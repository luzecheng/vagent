#!/usr/bin/env python3
"""Install/stop per-user macOS LaunchAgent for Codex read-only daemon."""
import argparse, os, pathlib, plistlib, shutil, subprocess, sys

LABEL="com.luzecheng.vagent.codex-readonly"
def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["install","uninstall","status"])
    p.add_argument("--repo-path",default=str(pathlib.Path.home()/"vagent"))
    a=p.parse_args()
    if sys.platform!="darwin": p.error("macOS only")
    domain=f"gui/{os.getuid()}"
    target=pathlib.Path.home()/"Library/LaunchAgents"/(LABEL+".plist")
    if a.action=="status":
        subprocess.run(["launchctl","print",f"{domain}/{LABEL}"],check=False)
        return
    if a.action=="uninstall":
        subprocess.run(["launchctl","bootout",domain,str(target)],check=False)
        target.unlink(missing_ok=True)
        print("Worker LaunchAgent removed")
        return
    gh,codex=shutil.which("gh"),shutil.which("codex")
    if not gh or not codex: p.error("gh and codex must be on PATH")
    worker=pathlib.Path(__file__).with_name("codex_daemon.py").resolve()
    repo=pathlib.Path(a.repo_path).expanduser().resolve()
    if not worker.is_file() or not (repo/".git").exists(): p.error("worker and repository required")
    logs=pathlib.Path.home()/"Library/Logs/vagent-codex-worker"
    logs.mkdir(parents=True,exist_ok=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    path=":".join(dict.fromkeys([str(pathlib.Path(gh).parent),str(pathlib.Path(codex).parent),"/opt/homebrew/bin","/usr/local/bin","/usr/bin","/bin"]))
    data={"Label":LABEL,"ProgramArguments":[sys.executable,str(worker),"--repo-path",str(repo)],
          "EnvironmentVariables":{"PATH":path,"HOME":str(pathlib.Path.home())},
          "RunAtLoad":True,"KeepAlive":{"SuccessfulExit":False},
          "StandardOutPath":str(logs/"worker.log"),
          "StandardErrorPath":str(logs/"error.log")}
    subprocess.run(["launchctl","bootout",domain,str(target)],capture_output=True)
    tmp=target.with_suffix(".plist.tmp")
    with tmp.open("wb") as f: plistlib.dump(data,f)
    tmp.replace(target)
    r=subprocess.run(["launchctl","bootstrap",domain,str(target)],capture_output=True,text=True)
    if r.returncode: raise SystemExit("launchctl bootstrap failed: "+r.stderr[:300])
    print("LaunchAgent installed and started:",LABEL)
    print("Log directory:",logs)

if __name__=="__main__": main()
