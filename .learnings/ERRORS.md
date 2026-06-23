# Error Log

## [ERR-20260529-001] rg_access_denied

**Logged**: 2026-05-29T00:00:00+08:00
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
`rg --files` failed with access denied in the workspace shell.

### Error
```text
程序“rg.exe”无法运行: 拒绝访问。
```

### Context
- Command attempted: `rg --files`
- Workspace: `F:\Project\vibecoding-2`
- Fallback: PowerShell native file listing commands

### Suggested Fix
Use PowerShell `Get-ChildItem` fallback when `rg.exe` is unavailable or blocked on this machine.

### Metadata
- Reproducible: unknown
- Related Files: none

---

## [ERR-20260529-002] network_sandbox_blocked

**Logged**: 2026-05-29T00:00:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
The first `run-daily` attempt failed because the sandbox blocked outbound HTTPS sockets.

### Error
```text
urllib.error.URLError: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>
```

### Context
- Command attempted: `python main.py run-daily --date 2026-05-29`
- The command needs access to arXiv, GitHub, and Hugging Face.
- Re-running with escalated network permission succeeded.

### Suggested Fix
For real data collection runs, allow `python main.py` to access the network.

### Metadata
- Reproducible: yes
- Related Files: `lab_radar/sources.py`

### Resolution
- **Resolved**: 2026-05-29T00:00:00+08:00
- **Notes**: Re-ran the command with escalated permissions and generated the first report.

---
