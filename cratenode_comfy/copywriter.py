"""Copy helpers through a local Ollama server: headlines, shorter text, taglines and
more, returned as a list of variants. Standard library only.

The model is always the user's choice (nothing is pulled or picked automatically).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

TASKS = {
    "headlines": "Write {count} short, punchy headlines for a graphic design, each at most {max_chars} "
                 "characters, based on the text below.",
    "shorten": "Rewrite the text below in {count} different ways, each at most {max_chars} characters, keeping "
               "its meaning and key words.",
    "subtitles": "Write {count} one-line subtitles (at most {max_chars} characters each) that support this "
                 "headline.",
    "taglines": "Write {count} memorable taglines (at most {max_chars} characters each) for the text below.",
    "calls to action": "Write {count} short calls to action for a button or banner (at most {max_chars} "
                       "characters each) based on the text below.",
    "custom": "Follow the instructions. Give {count} options, each at most {max_chars} characters.",
}
SYSTEM = ("You write copy for graphic designs. Reply with the options only: one per line, no numbering, no quotes, "
          "no explanations, no emoji unless asked.")


def build_prompt(task: str, text: str, instructions: str = "", count: int = 3, max_chars: int = 60) -> str:
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; use one of {', '.join(TASKS)}")
    p = TASKS[task].format(count=count, max_chars=max_chars)
    if instructions.strip():
        p += "\nInstructions: " + instructions.strip()
    if text.strip():
        p += "\n\nText:\n" + text.strip()
    return p


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_LEAD = re.compile(r"^\s*(?:[-*•]+|\d+[.):]|\(\d+\))\s*")


def parse_variants(reply: str, max_chars: int = 0) -> tuple[list[str], list[str]]:
    """(fitting, too_long): one option per line, numbering / bullets / quotes removed."""
    reply = _THINK.sub("", reply)
    out, long_ = [], []
    for line in reply.splitlines():
        s = _LEAD.sub("", line).strip().strip('"“”\'').strip()
        if not s or s.endswith(":") and len(s) < 40 and not out:  # a preamble like "Here are 3 headlines:"
            continue
        if s not in out and s not in long_:
            (long_ if max_chars and len(s) > max_chars else out).append(s)
    return out, long_


LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def check_host(host: str, allowed: list | None = None) -> None:
    """Only this machine, unless the config lists other hosts (allowed_hosts), so a workflow
    shared by someone else can't send text to a server of their choosing."""
    from urllib.parse import urlparse

    u = urlparse(host.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError(f"host must be an http(s) URL like http://127.0.0.1:11434, not {host!r}")
    name = u.hostname.lower()
    if name not in LOOPBACK and name not in {h.lower() for h in (allowed or [])}:
        raise PermissionError(f"Copy Writer only talks to this machine by default; add {name!r} to "
                              f"allowed_hosts in the CrateNode-Comfy config to use that server")


def generate(host: str, model: str, prompt: str, system: str = SYSTEM, temperature: float = 0.7, seed: int = 0,
             timeout: float = 120.0, allowed_hosts: list | None = None) -> str:
    if not model.strip():
        raise ValueError("choose an Ollama model (the name shown by 'ollama list')")
    check_host(host, allowed_hosts)
    body = json.dumps({"model": model.strip(), "prompt": prompt, "system": system, "stream": False,
                       "options": {"temperature": temperature, "seed": int(seed)}}).encode()
    req = urllib.request.Request(host.rstrip("/") + "/api/generate", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama not reachable at {host}: {e.reason}") from None
    if "error" in d:
        raise RuntimeError(f"Ollama: {d['error']}")
    return d.get("response", "")


def write(task: str, text: str, model: str, host: str = "http://127.0.0.1:11434", instructions: str = "",
          count: int = 3, max_chars: int = 60, temperature: float = 0.7, seed: int = 0,
          allowed_hosts: list | None = None) -> tuple[list[str], str]:
    """(variants, report). Variants longer than max_chars are dropped (reported); if none
    fit, the shortest ones are returned so the graph still runs."""
    reply = generate(host, model, build_prompt(task, text, instructions, count, max_chars),
                     temperature=temperature, seed=seed, allowed_hosts=allowed_hosts)
    fit, long_ = parse_variants(reply, max_chars)
    variants = fit[:count] or sorted(long_, key=len)[:count]
    if not variants:
        raise RuntimeError("the model returned no usable lines")
    report = f"{len(fit)} fit {max_chars} characters" + (f", {len(long_)} too long" if long_ else "")
    if not fit:
        report += " (using the shortest)"
    return variants, report
