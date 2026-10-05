// Trusted observer for the pinned Clang 17 analyzer pass. No target plugins.
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Basic/LangStandard.h"
#include "clang/Basic/SourceManager.h"
#include "clang/Lex/PPCallbacks.h"
#include "clang/Lex/Preprocessor.h"
#include "clang/StaticAnalyzer/Core/Checker.h"
#include "clang/StaticAnalyzer/Core/CheckerManager.h"
#include "clang/StaticAnalyzer/Core/PathSensitive/AnalysisManager.h"
#include "clang/StaticAnalyzer/Frontend/CheckerRegistry.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <map>
#include <memory>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
using namespace clang;
using namespace clang::ento;
namespace {
struct Counts {
  uint64_t Entered = 0, DeclNodes = 0, StmtNodes = 0, BodyCallbacks = 0;
  bool InitiallySystem = false, SystemHeaderPragma = false;
};
struct Observation {
  std::map<std::string, Counts> Files;
  std::string Source, Standard, Context;
  size_t PathBytes = 0;
  bool Overflow = false, TUStarted = false, TUEnded = false, Errors = false;
  bool Written = false;
  const DiagnosticsEngine *Diagnostics = nullptr;
  Counts *file(SourceManager &SM, FileID FID) {
    const FileEntry *FE = SM.getFileEntryForID(FID);
    if (!FE) return nullptr; // Builtins and command-line pseudo-buffers.
    std::string Name = FE->getName().str();
    if (Name.empty() || Name.size() > 4096) { Overflow = true; return nullptr; }
    auto Found = Files.find(Name);
    if (Found != Files.end()) return &Found->second;
    if (Files.size() >= 4096 || PathBytes + Name.size() > 512 * 1024) {
      Overflow = true; return nullptr;
    }
    PathBytes += Name.size();
    auto &Value = Files[Name];
    Value.InitiallySystem = SM.isInSystemHeader(SM.getLocForStartOfFile(FID));
    return &Value;
  }
  void node(SourceManager &SM, SourceLocation Loc, bool DeclNode) {
    if (Loc.isInvalid()) return;
    // Physical spelling and expansion IDs. PresumedLoc/#line is never used.
    SourceLocation S = SM.getSpellingLoc(Loc), E = SM.getExpansionLoc(Loc);
    FileID SF = SM.getFileID(S), EF = SM.getFileID(E);
    if (auto *V = file(SM, SF)) { if (DeclNode) ++V->DeclNodes; else ++V->StmtNodes; }
    if (SF != EF) if (auto *V = file(SM, EF)) { if (DeclNode) ++V->DeclNodes; else ++V->StmtNodes; }
  }
  void write() {
    if (Written) return;
    Written = true;
    if (Diagnostics) Errors = Diagnostics->hasErrorOccurred();
    const char *Output = std::getenv("NICO_CLANG_HEADER_OUTPUT");
    if (!Output || !*Output) return;
    llvm::json::Array Rows;
    for (const auto &Item : Files) {
      const auto &V = Item.second;
      Rows.push_back(llvm::json::Object{{"path", Item.first}, {"entered", V.Entered},
        {"ast_decl_nodes", V.DeclNodes}, {"ast_stmt_nodes", V.StmtNodes},
        {"ast_body_callbacks", V.BodyCallbacks}, {"initially_system", V.InitiallySystem},
        {"system_header_pragma_observed", V.SystemHeaderPragma}});
    }
    llvm::json::Object Document{{"schema", "nico.clang-header-observer.v1"},
      {"clang_version", CLANG_VERSION_STRING}, {"source", Source}, {"standard", Standard},
      {"context_id", Context}, {"translation_unit_started", TUStarted},
      {"translation_unit_ended", TUEnded}, {"diagnostic_errors", Errors},
      {"observation_overflow", Overflow}, {"files", std::move(Rows)}};
    std::string Bytes; llvm::raw_string_ostream Stream(Bytes);
    Stream << llvm::json::Value(std::move(Document)); Stream.flush();
    if (Bytes.empty() || Bytes.size() > 1024 * 1024) return;
    int FD = ::open(Output, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (FD < 0) return;
    size_t Position = 0;
    while (Position < Bytes.size()) {
      ssize_t Count = ::write(FD, Bytes.data() + Position, Bytes.size() - Position);
      if (Count < 0 && errno == EINTR) continue;
      if (Count <= 0) break;
      Position += static_cast<size_t>(Count);
    }
    ::close(FD); // Missing/partial output is rejected independently by the consumer.
  }
};
class ParsedVisitor : public RecursiveASTVisitor<ParsedVisitor> {
  Observation &State; SourceManager &SM;
public:
  ParsedVisitor(Observation &State, SourceManager &SM) : State(State), SM(SM) {}
  bool VisitDecl(Decl *D) { State.node(SM, D->getLocation(), true); return !State.Overflow; }
  bool VisitStmt(Stmt *S) { State.node(SM, S->getBeginLoc(), false); return !State.Overflow; }
};
class EnteredFiles : public PPCallbacks {
  std::shared_ptr<Observation> State; SourceManager &SM;
public:
  EnteredFiles(std::shared_ptr<Observation> State, SourceManager &SM) : State(State), SM(SM) {}
  void FileChanged(SourceLocation Loc, FileChangeReason Reason,
      SrcMgr::CharacteristicKind, FileID) override {
    if (Reason != SystemHeaderPragma || Loc.isInvalid()) return;
    if (auto *V = State->file(SM, SM.getFileID(SM.getExpansionLoc(Loc))))
      V->SystemHeaderPragma = true;
  }
  void LexedFileChanged(FileID FID, LexedFileChangeReason Reason,
      SrcMgr::CharacteristicKind, FileID, SourceLocation) override {
    if (Reason != LexedFileChangeReason::EnterFile) return;
    if (auto *V = State->file(SM, FID)) ++V->Entered;
    if (FID == SM.getMainFileID()) if (const FileEntry *FE = SM.getFileEntryForID(FID))
      State->Source = FE->getName().str();
  }
};
class HeaderObserver : public Checker<check::ASTDecl<TranslationUnitDecl>,
                                     check::ASTCodeBody, check::EndOfTranslationUnit> {
public:
  std::shared_ptr<Observation> State;
  ~HeaderObserver() { if (State) State->write(); }
  void checkASTDecl(const TranslationUnitDecl *TU, AnalysisManager &Mgr, BugReporter &) const {
    State->TUStarted = true;
    ParsedVisitor Visitor(*State, Mgr.getSourceManager());
    Visitor.TraverseDecl(const_cast<TranslationUnitDecl *>(TU));
  }
  void checkASTCodeBody(const Decl *D, AnalysisManager &Mgr, BugReporter &) const {
    auto &SM = Mgr.getSourceManager();
    const Stmt *Body = D->getBody();
    auto L = SM.getExpansionLoc(Body ? Body->getBeginLoc() : D->getLocation());
    if (L.isValid()) if (auto *V = State->file(SM, SM.getFileID(L))) ++V->BodyCallbacks;
  }
  void checkEndOfTranslationUnit(const TranslationUnitDecl *, AnalysisManager &Mgr,
                                BugReporter &) const {
    State->TUEnded = true;
    State->Errors = Mgr.getASTContext().getDiagnostics().hasErrorOccurred();
    State->write();
  }
};
void registerObserver(CheckerManager &Mgr) {
  auto *Checker = Mgr.registerChecker<HeaderObserver>();
  Checker->State = std::make_shared<Observation>();
  auto &State = *Checker->State;
  State.Diagnostics = &Mgr.getDiagnostics();
  if (const char *ID = std::getenv("NICO_CLANG_HEADER_CONTEXT")) State.Context = ID;
  State.Standard = LangStandard::getLangStandardForKind(Mgr.getLangOpts().LangStd).getName();
  // In this pinned lifecycle, registration precedes ParseAST/main-file entry.
  // addPPCallbacks chains existing callbacks; it never replaces a token watcher.
  auto &PP = const_cast<Preprocessor &>(Mgr.getPreprocessor());
  PP.addPPCallbacks(std::make_unique<EnteredFiles>(Checker->State, PP.getSourceManager()));
}
bool shouldRegister(const CheckerManager &) { return true; }
}
extern "C" const char clang_analyzerAPIVersionString[] = CLANG_ANALYZER_API_VERSION_STRING;
extern "C" void clang_registerCheckers(CheckerRegistry &Registry) {
  Registry.addChecker(registerObserver, shouldRegister, "nico.HeaderEvidence",
    "Records physical analyzer input and callback membership only", "", false);
}
