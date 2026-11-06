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

- Open a pull request from the task branch into the correct product-line stable branch; provide a clear summary and test results.
- Windows task branches target `main`. Linux task branches target `linux` exclusively. The strict Linux isolation rules in Section 8 take precedence over any generic branching guidance in this document.
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

## 7. Release Notes and Version Communication

- Whenever code or documentation changes are merged into `main`, update `ReleaseNote.md` to record the user-facing changes included in that merge. Do not leave merged user-facing functionality undocumented.
- Before asking the user to create a release tag, identify and communicate the next release version based on the latest version in `ReleaseNote.md` (for example, `v1.7`).
- Keep the release-note version and the proposed Git tag name consistent. Explicitly tell the user the exact tag to create (for example, `v1.7`).
- Do not create or push a release tag unless the user explicitly asks you to do so.
- If a merge has already happened before its release-note entry is added, create a separate documentation branch and pull request to update `ReleaseNote.md`; do not commit directly to `main`.


## 8. Independent Linux Product Line — Strict Branch Isolation

The Linux/Ubuntu edition is a separate product line from the Windows edition. The two lines must remain independently maintained.

### 8.1 Branch Ownership and Direction

- `main` is the Windows stable branch only. It must not receive Linux product implementation, Linux-only configuration, Linux-only packaging, Linux-only CI workflows, or Linux-specific release documentation.
- `linux` is the Ubuntu/Linux stable branch only.
- The `linux` branch must NEVER be merged into `main`, directly or indirectly. This is a permanent repository rule, not a temporary release restriction.
- Never open or retarget a pull request from `linux` (or any Linux feature branch) to `main`.
- Never use a merge commit, squash merge, rebase, fast-forward, or any other integration method to bring Linux branch history into `main`.
- Do not use `main` as the target for Linux fixes, Linux releases, or Linux documentation.

### 8.2 Initial Baseline and Future Branching

- The `linux` branch may be created once from the then-current stable `main` commit as an initial code baseline. This one-time branch creation is not a merge.
- After that initial baseline, all Linux work must start from `linux` or from a feature branch created from `linux`.
- Use task branches such as `feature/linux-<name>`, `fix/linux-<name>`, and `docs/linux-<name>`.
- Every Linux pull request must target `linux`. Review and test it against the Linux branch before merge.
- Never create a Linux feature branch from `main` after the initial baseline has been established.

### 8.3 No Automatic Cross-Branch Synchronization

- Do not merge, rebase, or automatically sync `main` into `linux`, or `linux` into `main`.
- Windows changes do not automatically flow into the Linux product line.
- If a Windows-side bug fix or shared improvement is genuinely required by Linux, assess it separately and deliberately port only the necessary change to a Linux task branch. Re-implement or adapt it as needed for Linux, then test it independently.
- A Linux-specific change must never be copied back into `main`. If a genuinely platform-neutral improvement is needed on Windows, implement and review it as a separate Windows task on a Windows task branch, without merging Linux branch history.
- Do not cherry-pick commits across the two stable branches as a routine synchronization mechanism. Any exceptional cross-branch code transfer requires explicit user approval and must transfer only reviewed, platform-appropriate changes—not branch history or Linux-only files.

### 8.4 Platform Scope and Compatibility

- Keep Windows packaging, Windows runtime behaviour, and the Windows EXE workflow isolated from Linux packaging and runtime behaviour.
- Keep Linux packaging, Linux service integration, and Linux-only startup/configuration isolated to the `linux` branch.
- Shared, platform-neutral code may exist in both product lines, but each branch must be independently buildable and testable.
- Do not assume that a change tested on Windows is valid on Ubuntu, or vice versa.
- Validate Linux support on the declared Ubuntu versions and CPU architectures. Record which combinations were actually tested; do not claim untested combinations are supported.
- Linux executable artifacts must be built on compatible Linux runners/environments and separately for each supported CPU architecture. Do not attempt to reuse a Windows EXE as a Linux executable.

### 8.5 Independent CI, Releases, and Documentation

- Linux CI workflows must run for Linux branches and must not alter or weaken Windows CI workflows on `main`.
- Windows and Linux release versions, release notes, build artifacts, and tags are independent.
- Keep Windows release notes and tags on the Windows line (for example, `v1.7`) and Linux release notes and tags on the Linux line (for example, `linux-v1.0`).
- Linux release-note updates must be made on `linux` through its own task branch and pull request. Do not update Windows `ReleaseNote.md` on `main` for Linux-only changes.
- Do not publish or tag either product line without the user's explicit approval, and follow the release/version approval rules for that product line.

### 8.6 Mandatory Pre-PR and Pre-Merge Safety Checks

- Before creating or updating a Linux pull request, verify that its base is exactly `linux` and its head is a Linux task branch.
- Before any merge, verify the target branch again. If the target is `main` and the change belongs to the Linux product line, stop; do not merge.
- Inspect the changed-file list to ensure Linux-only files, workflows, packaging, and documentation are not being introduced into `main`.
- Never change `main` branch protection, CI triggers, or Windows release configuration to accommodate Linux work.
- If branch intent or platform ownership is ambiguous, stop and ask the user rather than guessing.
