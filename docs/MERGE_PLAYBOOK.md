# Phase 3 — Merge & Tag Playbook (v2.0.0)

This file lives at `docs/MERGE_PLAYBOOK.md` and exists *only* to keep the
exact commands you should run, in the order you should run them, on the
day you cut `v2.0.0`. Everything before this point is already on the
`feature/full-hardware-support` branch and pushed nowhere.

> Do NOT skip the verification checklist in
> `docs/RELEASE_NOTES_v2.0.0.md` ("Verification checklist used to cut
> this release") before running anything below. The plan-only build+run
> and the full colcon build are non-negotiable; the real-robot dry-run
> is mandatory IF you have hardware on hand.

---

## 1. Confirm the branch is clean and ahead of `main`

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop
git fetch origin
git status                                           # working tree clean
git checkout feature/full-hardware-support
git log --oneline main..HEAD                         # should show all P0/P1 commits
git diff --stat main..HEAD | tail -1                 # sanity: > a few thousand lines
git submodule status                                 # both submodules clean
```

## 2. Run the verification block from RELEASE_NOTES_v2.0.0.md

(See the section **"Verification checklist used to cut this release"** in
`docs/RELEASE_NOTES_v2.0.0.md`. Don't paraphrase it from memory; copy
it.)

## 3. Merge to `main` with `--no-ff` (preserve the feature branch)

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff feature/full-hardware-support \
    -m "Merge feature/full-hardware-support: v2.0.0 dual-track release"
```

If the merge surfaces any conflict (it shouldn't — `main` is just
`v1.1.0-review`), abort with `git merge --abort` and bring it up before
re-trying.

## 4. Tag

```bash
git tag -a v2.0.0 -m "v2.0.0 - dual-track plan-only + real-robot release"
git tag --list 'v2.0.0' -n100                        # confirm message
```

## 5. Push (branch + tag, in that order)

```bash
git push origin main
git push origin v2.0.0
git push origin feature/full-hardware-support        # keep the branch reachable
```

If you also want to delete the feature branch upstream after the merge:

```bash
git push origin --delete feature/full-hardware-support
```

(Local copies are kept; only the upstream ref is removed.)

## 6. Create the GitHub Release

```bash
gh release create v2.0.0 \
    --title "v2.0.0 - Full Hardware Support" \
    --notes-file docs/RELEASE_NOTES_v2.0.0.md \
    --target main
```

Or, if you don't have `gh` installed:

1. Open https://github.com/1douya1/safe-robotic-pouring/releases/new
2. Tag: `v2.0.0` (existing)
3. Target: `main`
4. Title: `v2.0.0 - Full Hardware Support`
5. Body: paste the contents of `docs/RELEASE_NOTES_v2.0.0.md`
6. **Uncheck** "Set as a pre-release".
7. Publish.

## 7. Sanity-check the release on a clean clone

```bash
cd /tmp && rm -rf rss-fresh && \
  git clone --branch v2.0.0 \
    https://github.com/1douya1/safe-robotic-pouring.git rss-fresh
cd rss-fresh
git submodule update --init --recursive
ls src/xarm_ros2/xarm_moveit_config/                 # non-empty
ls src/easy_handeye2/                                # non-empty
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to mtc_tutorial
source install/setup.bash
./scripts/run_demo.sh --plan-only                    # RViz comes up
```

If this final sanity check passes, the release is good. If not, do
**not** patch over it — pull the release, fix the issue on a new branch,
cut `v2.0.1`.

---

## Rollback

If something goes wrong after the tag is pushed:

```bash
# Option A: revert the merge commit on main, keep the tag (rare)
git checkout main && git revert -m 1 <merge-commit-sha>
git push origin main

# Option B: full rollback (delete tag + reset main to v1.1.0-review)
git push origin --delete v2.0.0
git tag -d v2.0.0
git checkout main
git reset --hard v1.1.0-review
git push --force-with-lease origin main             # only if absolutely required
```

Prefer Option A. Force-pushing `main` will rewrite history for everyone
who has cloned this repo and should be a last resort.
