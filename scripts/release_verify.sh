#!/usr/bin/env bash
# release_verify.sh — pre-release / pre-public-flip verification (launch Gate N).
#
# Runs the mechanical checks that can be automated, and prints a checklist for
# the manual / maintainer-only / repo-public-gated items. Safe to run anytime;
# read-only except for a throwaway build dir + temp venv, both cleaned up.
#
# Usage:  ./scripts/release_verify.sh
# Exit:   non-zero if any HARD check fails; SKIP/MANUAL items never fail the run.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

# ---- pretty output --------------------------------------------------------
if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[34m'; D=$'\033[2m'; Z=$'\033[0m'
else G=; R=; Y=; B=; D=; Z=; fi
fails=0
pass() { printf "  ${G}PASS${Z}  %s\n" "$1"; }
fail() { printf "  ${R}FAIL${Z}  %s\n" "$1"; fails=$((fails+1)); }
skip() { printf "  ${Y}SKIP${Z}  %s ${D}(%s)${Z}\n" "$1" "$2"; }
sec()  { printf "\n${B}== %s ==${Z}\n" "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---- 1. version -----------------------------------------------------------
sec "Package version"
VER=$(grep -E '^version = ' pyproject.toml | head -1 | sed -E 's/.*"(.*)".*/\1/')
printf "  pyproject version: ${B}%s${Z}\n" "$VER"
case "$VER" in
  "")                 fail "could not read version from pyproject.toml" ;;
  *rc*|*a*|*b*|*dev*) skip "version is a pre-release ($VER)" "promote to a stable X.Y.Z for a public launch" ;;
  *)                  pass "version is a stable release string ($VER)" ;;
esac

# ---- 2. build + twine check ----------------------------------------------
sec "Build + metadata (python -m build, twine check)"
if have python3 && python3 -c 'import build' 2>/dev/null; then
  rm -rf dist build ./*.egg-info
  if python3 -m build >/tmp/rv_build.log 2>&1; then
    pass "python -m build produced sdist + wheel"
    ls dist/ | sed 's/^/        /'
    if python3 -c 'import twine' 2>/dev/null; then
      if python3 -m twine check dist/* >/tmp/rv_twine.log 2>&1; then pass "twine check"
      else fail "twine check — see /tmp/rv_twine.log"; tail -3 /tmp/rv_twine.log | sed 's/^/        /'; fi
    else skip "twine check" "pip install twine"; fi
  else fail "python -m build — see /tmp/rv_build.log"; tail -4 /tmp/rv_build.log | sed 's/^/        /'; fi
else skip "build + twine" "pip install build twine"; fi

# ---- 3. fresh-venv install smoke -----------------------------------------
sec "Fresh-venv install smoke (as a user would)"
if [ -d dist ] && ls dist/*.whl >/dev/null 2>&1; then
  VROOT=$(mktemp -d); VENV="$VROOT/venv"
  if python3 -m venv "$VENV" 2>/dev/null; then
    if "$VENV/bin/pip" install --quiet dist/*.whl 2>/tmp/rv_pip.log; then
      pass "pip install <wheel> in a clean venv"
      out=$("$VENV/bin/whiz" --version 2>&1)
      if echo "$out" | grep -q "whizzard $VER"; then pass "whiz --version reports $VER"
      else fail "whiz --version = '$out' (expected 'whizzard $VER')"; fi
      if "$VENV/bin/whiz" --help >/dev/null 2>&1; then pass "whiz --help runs"
      else fail "whiz --help crashed"; fi
    else fail "pip install failed — see /tmp/rv_pip.log"; fi
    rm -rf "$VROOT"
  else skip "install smoke" "python venv unavailable"; fi
else skip "install smoke" "no wheel built (see build step)"; fi
printf "  ${D}note: cross-platform install (incl. Windows) → dispatch the install-smoke workflow${Z}\n"

# ---- 4. workflow hardening -----------------------------------------------
sec "GitHub Actions hardening"
# A pinned action ref is a 40-char hex SHA. Flag any `uses: owner/action@ref`
# whose ref is not a 40-hex SHA (a version tag or branch). (Local `./` and
# `docker://` uses have no `@` and are skipped.)
unpinned=$(grep -rEn "uses:[[:space:]]+[^ ]+@" .github/workflows/ 2>/dev/null | while IFS= read -r line; do
  ref=$(printf '%s' "$line" | sed -E 's/.*@([^[:space:]#]+).*/\1/')
  printf '%s' "$ref" | grep -qE '^[0-9a-f]{40}$' || printf '%s\n' "$line"
done)
if [ -n "$unpinned" ]; then
  fail "some actions are not pinned to a commit SHA:"
  printf '%s\n' "$unpinned" | sed 's/^/        /'
else pass "every third-party action is pinned to a 40-char commit SHA"; fi
if grep -rEn "pull_request_target" .github/workflows/ >/dev/null 2>&1; then
  fail "pull_request_target present — confirm it never checks out untrusted head with write perms"
  grep -rEn "pull_request_target" .github/workflows/ | sed 's/^/        /'
else pass "no pull_request_target usage"; fi
missing_perms=0
for wf in .github/workflows/*.yml; do
  grep -qE "^permissions:" "$wf" || { fail "no top-level permissions: block in $(basename "$wf")"; missing_perms=1; }
done
[ "$missing_perms" = 0 ] && pass "every workflow declares a top-level permissions: block"
if have actionlint; then
  if actionlint .github/workflows/*.yml >/tmp/rv_al.log 2>&1; then pass "actionlint clean"
  else fail "actionlint findings — see /tmp/rv_al.log"; fi
else skip "actionlint" "install rhysd/actionlint to lint workflows locally"; fi

# ---- 5. GitHub repo state (needs gh + auth) ------------------------------
sec "GitHub repo state"
if have gh && gh auth status >/dev/null 2>&1; then
  REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)
  health=$(gh api "repos/$REPO/community/profile" --jq .health_percentage 2>/dev/null)
  if [ "$health" = "100" ]; then pass "community health profile = 100%"
  else skip "community health = ${health:-unknown}%" "aim for 100"; fi
  vis=$(gh repo view --json visibility --jq .visibility 2>/dev/null)
  printf "  repo visibility: ${B}%s${Z}\n" "$vis"
  if [ "$vis" = "PUBLIC" ]; then
    if gh api "repos/$REPO/branches/main/protection" >/dev/null 2>&1; then pass "branch protection on main is configured"
    else fail "main has no branch protection (repo is public — configure it)"; fi
  else
    skip "branch protection" "gated: only configurable once the repo is public (free plan)"
  fi
else skip "repo-state checks" "gh not installed or not authenticated"; fi

# ---- 6. manual / maintainer checklist ------------------------------------
sec "Manual — verify by hand before flipping public"
cat <<'EOF'
  [ ] Signed commits: git log --show-signature -5 on main shows good signatures (gitsign/GPG set up)
  [ ] Branch protection (at flip): require PR + 1 approval, dismiss stale, signed commits,
      no force-push/deletion, enforce admins
  [ ] Enable secret scanning + push protection, and Private Vulnerability Reporting (Settings → Code security)
  [ ] gh secret list — every secret has a reason; no stale ones
  [ ] PyPI Trusted Publishing registered for the repo → release.yml
  [ ] bumblebee baseline on the dev machine — no compromised packages / MCP configs / extensions
  [ ] Re-read the README cold: is the value proposition clear in 30 seconds?
  [ ] Tabletop: "if my dev machine were fully compromised right now, what could an attacker do?"
      — each answer should map to a control that bounds the blast radius
EOF

# ---- summary --------------------------------------------------------------
rm -rf dist build ./*.egg-info 2>/dev/null
sec "Summary"
if [ "$fails" -eq 0 ]; then printf "  ${G}All automated checks passed.${Z} Work the manual list above, then flip.\n"; exit 0
else printf "  ${R}%d automated check(s) failed.${Z} Resolve before releasing.\n" "$fails"; exit 1; fi
