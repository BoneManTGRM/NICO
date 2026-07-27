# Mobile proof JavaScript syntax hotfix

The post-merge production proof failed because the terminal-metrics JavaScript arrow function closed with an extra parenthesis. The proof reached Playwright evaluation and raised `SyntaxError: Unexpected token ')'`.

This hotfix removes the extra parenthesis and adds a regression guard that rejects the invalid closure.
