#include "tokenlist.h"
const std::vector<Token*>* TokensFrontBack::lessTokens()
{
    if (mLessDisabled)
        return nullptr;
    if (!mLessValid) {
        // Only a fresh query may rebuild; never refresh an in-flight cursor.
        // One lifetime attempt bounds all extra full-list construction work.
        if (mLessRebuildPending) {
            if (mLessRebuildAttempted) {
                invalidateLessTokens();
                return nullptr;
            }
            mLessRebuildAttempted = true;
        }
        try {
            std::vector<Token*> tokens;
            std::unordered_map<Token*, std::size_t> slots;
            for (Token* token = front; token; token = token->next()) {
                if (token->str() == "<") {
                    slots.emplace(token, tokens.size());
                    tokens.push_back(token);
                }
            }
            mLessTokens.swap(tokens);
            mLessSlots.swap(slots);
            mLessValid = true;
            mLessRebuildPending = false;
        } catch (const std::bad_alloc&) {
            invalidateLessTokens();
            mLessDisabled = true;
            return nullptr;
        }
    }
    return &mLessTokens;
}

void TokensFrontBack::invalidateLessTokens()
{
    // Unsupported mutations permanently restore linear traversal for this list.
    mLessDisabled = mLessDisabled || mLessValid || mLessRebuildPending;
    mLessRebuildPending = false;
    mLessValid = false;
    mLessTokens.clear();
    mLessSlots.clear();
}

void TokensFrontBack::removedLessToken(Token* token)
{
    if (!mLessValid)
        return;
    const auto it = mLessSlots.find(token);
    if (it != mLessSlots.end()) {
        mLessTokens[it->second] = nullptr;
        mLessSlots.erase(it);
        // Bound tombstone traversal by twice the live candidate population.
        if (mLessTokens.size() - mLessSlots.size() > mLessSlots.size())
            invalidateLessTokens();
    }
}

void TokensFrontBack::changedLessToken(Token* token)
{
    if (mLessRebuildPending && token && token->str() == "<" &&
        (token == front || token->previous() || token->next())) {
        // The empty pending cache cannot certify an attached token's identity.
        // Unlinked construction is handled after insertion installs its links.
        invalidateLessTokens();
        return;
    }
    if (!mLessValid)
        return;
    if (token->str() != "<") {
        removedLessToken(token);
    } else if ((token == front || token->previous() || token->next()) &&
               mLessSlots.find(token) == mLessSlots.end()) {
        // An existing token became '<'. Its lexical position is not cached.
        invalidateLessTokens();
    }
}

void TokensFrontBack::insertedLessToken(Token* token)
{
    if (!mLessValid || token->str() != "<")
        return;
    if (token != back) {
        if (mLessRebuildAttempted) {
            invalidateLessTokens();
        } else {
            // Invalidate immediately; the current caller resumes linearNext.
            // Further insertions/deletions are safe while both caches are empty.
            mLessValid = false;
            mLessRebuildPending = true;
            mLessTokens.clear();
            mLessSlots.clear();
        }
        return;
    }
    try {
        mLessSlots.emplace(token, mLessTokens.size());
        mLessTokens.push_back(token);
    } catch (const std::bad_alloc&) {
        // Index allocation must not turn a successful token edit into failure.
        invalidateLessTokens();
        mLessDisabled = true;
    }
}
