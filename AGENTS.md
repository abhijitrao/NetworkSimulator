# Repository Development Rules

These rules are mandatory for all future work on this repository.

## 1. Branching

- Never develop a feature, fix, refactor, or documentation change directly on `main`.
- Create a dedicated branch for each task (for example, `feature/<short-name>`, `fix/<short-name>`, or `docs/<short-name>`).
- Keep changes scoped to the requested task.

## 2. Preserve Existing Behaviour

- Do not change existing business logic or established behaviour unless the user explicitly requests it.
- Avoid unrelated refactoring and unrelated file changes.
- Maintain backward compatibility where applicable.
- Add or update tests for changed behaviour.

## 3. Validation Before Review

- Run the relevant automated tests and checks before requesting review.
- Verify the affected functionality and regression-sensitive existing features.
- Report test results honestly; clearly identify anything not tested or any known limitation.
- Do not describe a change as final or release-ready until validation is complete.

## 4. Pull Request and Merge Approval

- Open a pull request from the task branch into `main`; provide a clear summary and test results.
- Keep the pull request available for the user to review and test.
- **Never merge a pull request into `main` based only on phrases such as "continue", "go ahead", or approval to proceed with development/testing.**
- Merge only after the user explicitly approves the merge, using an unambiguous instruction such as "merge this PR into main".
- If approval is unclear, ask before merging.
- Do not push commits directly to `main` or bypass the pull-request review process.

## 5. Release and Windows EXE

- Build or publish a release EXE only after the user explicitly approves merging the completed changes into `main`.
- After the merge, verify that the Windows build workflow completed successfully and that the expected artifact was uploaded.
- Do not claim the EXE is ready until the artifact is confirmed.

## 6. Communication

- Before implementation, briefly confirm the intended scope when it is not clear.
- Explain what changed, what was tested, and provide the PR link.
- Clearly separate "implementation complete", "ready for user review", "approved to merge", and "release verified" as different states.

These rules apply to every future task in this repository unless the user explicitly changes them.
