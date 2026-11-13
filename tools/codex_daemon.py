#!/usr/bin/env python3
"""Conservative, opt-in, read-only GitHub issue queue for Mac Codex."""
import argparse, json, os, pathlib, subprocess, time

REPO="luzecheng/vagent"
OWNER="luzecheng"
APPROVAL="<!-- codex-worker-readonly-approved-v1 -->"
RESULT="<!-- codex-worker-readonly-result-v2 -->"
PROMPT=("Inspect this repository read-only. Report current branch, git status and whether "
        "skill/make-video/SKILL.md exists. Do not modify files or access secrets.")

def command(argv, timeout=40, cwd=None):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, cwd=cwd)

def api(path):
    r=command(["gh","api",path])
    if r.returncode: raise RuntimeError("GitHub API unavailable")
    return json.loads(r.stdout)

def authorized(issue):
    return (issue.get("state")=="open" and "pull_request" not in issue
            and issue.get("user",{}).get("login","").lower()==OWNER
            and APPROVAL in (issue.get("body") or ""))

def completed(number):
    page=1
    while True:
        batch=api(f"repos/{REPO}/issues/{number}/comments?per_page=100&page={page}")
        if any(RESULT in (c.get("body") or "") for c in batch): return True
        if len(batch)<100: return False
        page+=1

def post(number, status, code):
    body=(f"{RESULT}\n### Mac Codex daemon: {status}\n"
          f"- Fixed read-only task; exit_code={code}\n"
          "- Raw agent output not published.\n")
    r=command(["gh","issue","comment",str(number),"-R",REPO,"--body",body],timeout=45)
    if r.returncode: raise RuntimeError("GitHub comment failed")

def process(issue, repo, state, dry_run=False):
    if not authorized(issue): return "unauthorized"
    number=issue["number"]
    if completed(number): return "completed"
    claim=state/f"issue-{number}.claimed"
    if claim.exists(): return "claimed"
    if dry_run: return "ready"
    try: fd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError: return "claimed"
    with os.fdopen(fd,"w") as f: f.write(str(time.time()))
    try:
        r=command(["codex","exec","-s","read-only",PROMPT],timeout=300,cwd=repo)
        post(number,"PASS" if r.returncode==0 else "FAIL",r.returncode)
        return "reported"
    except subprocess.TimeoutExpired:
        try: post(number,"TIMEOUT","timeout")
        except Exception: pass
        return "timeout"
    except Exception as e:
        print(f"#{number}: {type(e).__name__}; claim retained",flush=True)
        return "error"

def cycle(repo,state,dry_run=False):
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    issues=api(f"repos/{REPO}/issues?state=open&per_page=100&sort=created&direction=desc")
    for issue in reversed(issues):
        if authorized(issue):
            print(f"#{issue['number']}: {process(issue,repo,state,dry_run)}",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo-path",default=str(pathlib.Path.home()/"vagent"))
    p.add_argument("--interval",type=int,default=60)
    p.add_argument("--once",action="store_true")
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    repo=pathlib.Path(a.repo_path).expanduser().resolve()
    if not (repo/".git").exists(): p.error("Git checkout required")
    state=pathlib.Path.home()/".local/state/vagent-codex-worker-v2"
    while True:
        try: cycle(repo,state,a.dry_run)
        except Exception as e: print(f"poll error: {type(e).__name__}: {str(e)[:120]}",flush=True)
        if a.once or a.dry_run: break
        time.sleep(max(30,a.interval))

if __name__=="__main__": main()
