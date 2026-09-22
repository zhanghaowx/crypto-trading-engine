### Summary :memo:
_Write an overview about it._

### Details
_Describe more what you did on changes._
1. (...)
2. (...)

### Bugfixes :bug: (delete if dind't have any)
-

### Architecture
- [ ] No new or moved package or module
- [ ] This PR adds or moves package/module structure

If it does:

- Responsibility:
- Why this directory owns it:
- Existing alternatives considered:

Include the before/after package tree when the directory structure
materially changes.

### Dependency check
- [ ] engine does not depend on dashboard, CLI or analysis
- [ ] analysis does not depend on dashboard
- [ ] reusable calculations are not embedded in UI code
- [ ] the dashboard only reads engine recordings
- [ ] tests mirror the source package
- [ ] AGENTS.md still describes where things live

A module reaching 400-500 lines is a prompt to ask what it owns, not an
automatic failure. The question to ask of any new code is: could this be
reused without the package it is in? If yes, reconsider the package.

### Checks
- [ ] Closed #798
- [ ] Tested Changes
- [ ] Stakeholder Approval
