#!/usr/bin/env python3
"""infra-drift: is what runs on this host what the repo says? Read-only.

Runs ON a host (via host-run). Stdlib only (the mini has Python 3.9).

    drift.py --checkout ~/agentic-ai-homelab                 # the mini
    drift.py --checkout /home/ops/agentic-ai-homelab --as ops  # the DGX (checkout owned by ops)
    drift.py --checkout ~/agentic-ai-homelab --checkout ~/chipi-infra   # several checkouts, one run

Reports, then ends with "DRIFT: N finding(s)" (exit 1 if any):
  1. checkout: commits behind/ahead of origin/main after a fetch; modified and untracked files;
  2. containers started from compose files under the checkout: running image != the image the
     compose file names now;
  3. images running as :latest or with no tag (any pull/recreate can change them silently);
  4. stray compose files in the home directory (depth <= 2) that define a container_name which is
     running from a DIFFERENT compose file (the 2026-10-17 ~/umami case).
"""
import argparse, glob, json, os, re, shutil, subprocess, sys

findings = []
ALLOW_UNPINNED = set()


def note(kind, msg):
    findings.append((kind, msg))
    print(f"  [DRIFT] {kind}: {msg}")


def run(cmd, user=None, cwd=None):
    if user:
        cmd = ["sudo", "-n", "-u", user] + cmd
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def docker_bin():
    return shutil.which("docker") or "/usr/local/bin/docker"


def check_checkout(path, user):
    print(f"== checkout {path}" + (f" (as {user})" if user else ""))
    g = ["git", "-C", path]
    rc, _, err = run(g + ["fetch", "-q", "origin"], user)
    if rc:
        note("checkout", f"git fetch failed: {err[:120]}")
        return
    _, br, _ = run(g + ["rev-parse", "--abbrev-ref", "HEAD"], user)
    _, counts, _ = run(g + ["rev-list", "--left-right", "--count", "HEAD...origin/main"], user)
    ahead, behind = (counts.split() + ["?", "?"])[:2]
    print(f"  branch {br}: ahead {ahead}, behind {behind} origin/main")
    if behind not in ("0", "?"):
        note("checkout", f"{behind} commit(s) behind origin/main: pull as the owner "
                         f"(`git -C {path} pull --ff-only`), never copy files in")
    if ahead not in ("0", "?"):
        note("checkout", f"{ahead} local commit(s) not on origin/main")
    _, st, _ = run(g + ["status", "--porcelain"], user)
    mod = [l for l in st.splitlines() if l and not l.startswith("??")]
    unt = [l for l in st.splitlines() if l.startswith("??")]
    if mod:
        same = []
        for l in mod:
            f = l[3:]
            rc, _, _ = run(g + ["diff", "--quiet", "origin/main", "--", f], user)
            same.append((f, rc == 0))
        for f, s in same:
            note("checkout", f"modified {f}" + (" (identical to origin/main: copied in by hand)" if s else ""))
    for l in unt:
        note("checkout", f"untracked {l[3:]}")
    if not mod and not unt:
        print("  clean")


def containers():
    rc, out, err = run([docker_bin(), "ps", "--format", "{{json .}}"])
    if rc:
        print(f"  docker ps failed: {err[:120]}")
        return []
    res = []
    for line in out.splitlines():
        c = json.loads(line)
        rc, ins, _ = run([docker_bin(), "inspect", c["Names"], "--format",
                          '{{json .Config.Labels}}|{{.Config.Image}}|{{.Image}}'])
        labels_s, image, image_id = (ins.split("|") + ["", "", ""])[:3]
        labels = json.loads(labels_s or "{}") or {}
        rc, rd, _ = run([docker_bin(), "image", "inspect", image_id, "--format", "{{json .RepoDigests}}"])
        digests = [d.split("@", 1)[1] for d in (json.loads(rd) if rc == 0 and rd else []) if "@" in d]
        res.append({"name": c["Names"], "image": image, "digests": digests,
                    "workdir": labels.get("com.docker.compose.project.working_dir", ""),
                    "files": labels.get("com.docker.compose.project.config_files", ""),
                    "service": labels.get("com.docker.compose.service", "")})
    return res


def compose_images(workdir, files, user):
    cmd = [docker_bin(), "compose", "--project-directory", workdir]
    for f in files.split(","):
        if f:
            cmd += ["-f", f]
    rc, out, err = run(cmd + ["config", "--format", "json"], user)
    if rc:
        return None, err[:160]
    cfg = json.loads(out)
    return {svc: (s.get("container_name") or svc, s.get("image", "")) for svc, s in cfg.get("services", {}).items()}, ""


def same_image(want, c):
    """The compose image matches what runs: same reference, or a pinned digest the container has."""
    if want == c["image"]:
        return True
    if "@sha256:" in want:
        return want.split("@", 1)[1] in c["digests"]
    return False


def unpinned(ref):
    if "@sha256:" in ref:
        return False
    last = ref.rsplit("/", 1)[-1]
    tag = last.rsplit(":", 1)[1] if ":" in last else ""
    return tag == "" or tag == "latest" or tag.endswith("-latest") or tag in ("main", "main-stable", "stable", "edge")


def check_containers(checkout, user, cs):
    print(f"== containers vs compose ({checkout})")
    stacks = {}
    for c in cs:
        if c["workdir"].startswith(os.path.realpath(checkout)) or c["workdir"].startswith(checkout):
            stacks.setdefault((c["workdir"], c["files"]), []).append(c)
    for (wd, files), members in sorted(stacks.items()):
        want, err = compose_images(wd, files, user)
        rel = os.path.relpath(wd, checkout)
        if want is None:
            note("compose", f"{rel}: `docker compose config` failed ({err})")
            continue
        for c in members:
            w = want.get(c["service"])
            if not w:
                note("compose", f"{rel}: container {c['name']} runs service {c['service']!r} that the compose file no longer defines")
            elif w[1] and not same_image(w[1], c):
                note("compose", f"{rel}: {c['name']} runs {c['image']} but compose names {w[1]}: recreate to apply")
            c["compose_image"] = w[1] if w else ""
        print(f"  {rel}: {len(members)} container(s) checked")


def check_unpinned(cs):
    print("== unpinned images (judged on what a recreate would pull)")
    for c in cs:
        ref = c.get("compose_image") or c["image"]
        if c["name"] in ALLOW_UNPINNED:
            if unpinned(ref):
                print(f"  allowed: {c['name']} ({ref})")
            continue
        if unpinned(ref):
            note("unpinned", f"{c['name']}: {ref} (a pull/recreate can change it silently)")


def check_strays(cs, checkouts):
    print("== stray compose files")
    running_from = {c["name"]: c["files"] for c in cs}
    home = os.path.expanduser("~")
    cands = set(glob.glob(os.path.join(home, "*", "docker-compose*.y*ml")) +
                glob.glob(os.path.join(home, "*", "*", "docker-compose*.y*ml")))
    reals = [os.path.realpath(c) for c in checkouts]
    n = 0
    for f in sorted(cands):
        if any(os.path.realpath(f).startswith(r) for r in reals):
            continue
        try:
            text = open(f, errors="ignore").read()
        except OSError:
            continue
        for name in re.findall(r"^\s*container_name:\s*['\"]?([\w.-]+)", text, re.M):
            src = running_from.get(name)
            if src and os.path.realpath(f) not in [os.path.realpath(x) for x in src.split(",")]:
                note("stray", f"{f} defines container {name!r}, which runs from {src}: delete or reconcile")
                n += 1
    if not n:
        print("  none")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", required=True, action="append",
                    help="a checkout on this host; repeat for several (e.g. homelab and chipi-infra)")
    ap.add_argument("--as", dest="user", help="OS user that owns the checkout (git + compose run as it)")
    ap.add_argument("--allow-unpinned", default="", help="comma-separated container names allowed to float (operator decision)")
    a = ap.parse_args()
    ALLOW_UNPINNED.update(x.strip() for x in a.allow_unpinned.split(",") if x.strip())
    checkouts = [os.path.expanduser(c) for c in a.checkout]
    cs = containers()
    for checkout in checkouts:
        check_checkout(checkout, a.user)
        check_containers(checkout, a.user, cs)
    check_unpinned(cs)
    check_strays(cs, checkouts)
    print(f"DRIFT: {len(findings)} finding(s)")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
