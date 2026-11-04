"""Build, install-check, and tag the GitHub packages. Uses only the standard library."""

import argparse
import hashlib
import json
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = {
    "sdk-python": "avp-sdk/python",
    "sdk-typescript": "avp-sdk/typescript",
    "cli": "avp-cli",
}


def run(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def package_version(package: str) -> str:
    directory = ROOT / PACKAGES[package]
    if package == "sdk-typescript":
        return json.loads((directory / "package.json").read_text())["version"]
    return tomllib.loads((directory / "pyproject.toml").read_text())["project"]["version"]


def release_tag(package: str) -> str:
    return f"{package}-v{package_version(package)}"


def package_for_tag(tag: str) -> str:
    for package in PACKAGES:
        if tag == release_tag(package):
            return package
    raise ValueError(f"tag {tag!r} does not match a package version")


def verify_install(package: str, archive: Path) -> None:
    """Install the artifact outside the checkout with its published dependencies."""
    with tempfile.TemporaryDirectory(prefix="avp-release-") as temp:
        consumer = Path(temp)
        if package == "sdk-typescript":
            (consumer / "package.json").write_text('{"private":true,"type":"module"}')
            run(
                "npm",
                "install",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                str(archive),
                cwd=consumer,
            )
            run(
                "node",
                "--input-type=module",
                "-e",
                """
import {parseCommission} from '@agent-voyager-project/sdk/commission';
import {bundledPrices} from '@agent-voyager-project/sdk/utils/pricing';
const c = parseCommission({avp_version:'0.1',run_id:'release',model:{provider:'openai',id:'test'},prompt:'Hi'});
if (c.run_id !== 'release' || !Object.keys(bundledPrices().models).length) process.exit(1);
""",
                cwd=consumer,
            )
        else:
            environment = consumer / "venv"
            run("uv", "venv", str(environment))
            python = environment / "bin/python"
            run("uv", "pip", "install", "--python", str(python), str(archive))
            distribution = "agent-voyager-project" if package == "sdk-python" else "avp-cli"
            run(
                str(python),
                "-I",
                "-c",
                f"""
from importlib.metadata import version
from avp.commission import Commission
from avp.utils.pricing import bundled_prices
assert version({distribution!r}) == {package_version(package)!r}
assert Commission(avp_version='0.1',run_id='release',model={{'provider':'openai','id':'test'}},prompt='Hi')
assert bundled_prices().models
""",
                cwd=consumer,
            )
            if package == "cli":
                run(str(environment / "bin/avp"), "--help", cwd=consumer)
                run(str(environment / "bin/avp"), "agent", "list", "--builtin", cwd=consumer)
                run(
                    str(python),
                    "-I",
                    "-c",
                    "from avp_cli.agents import builtins; "
                    "assert all((builtins.PACKAGE / 'dockerfiles' / (name + '.Dockerfile')).is_file() "
                    "for name in builtins.catalog().agents)",
                    cwd=consumer,
                )
                (consumer / "commission.json").write_text(
                    json.dumps(
                        {
                            "avp_version": "0.1",
                            "model": {"provider": "openai", "id": "test"},
                            "prompt": "Hi",
                        }
                    )
                )
                run(
                    str(environment / "bin/avp"),
                    "commission",
                    "check",
                    "commission.json",
                    cwd=consumer,
                )


def build(package: str, out: Path) -> None:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError(f"{out} must be empty")
    directory = ROOT / PACKAGES[package]
    if package == "sdk-typescript":
        run("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund", cwd=directory)
        run("npm", "pack", "--pack-destination", str(out), cwd=directory)
        archive = next(out.glob("*.tgz"))
    else:
        run("uv", "build", "--out-dir", str(out), cwd=directory)
        archive = next(out.glob("*.whl"))
    verify_install(package, archive)
    artifacts = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.iterdir())
    }
    manifest = {
        "package": package,
        "version": package_version(package),
        "tag": release_tag(package),
        "commit": run("git", "rev-parse", "HEAD"),
        "sha256": artifacts,
    }
    (out / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in artifacts.items())
    )
    print(f"Built and installed {release_tag(package)} in a clean environment")


def tag(package: str) -> None:
    if run("git", "status", "--porcelain"):
        raise ValueError("commit or remove working-tree changes before releasing")
    branch = run("git", "branch", "--show-current")
    if not branch:
        raise ValueError("release from a branch")
    run("git", "fetch", "origin", branch)
    if run("git", "rev-parse", "HEAD") != run("git", "rev-parse", f"origin/{branch}"):
        raise ValueError("push the branch before releasing")
    name = release_tag(package)
    if run("git", "ls-remote", "--tags", "origin", f"refs/tags/{name}"):
        raise ValueError(f"{name} already exists; bump the package version")
    run("git", "tag", "-a", name, "-m", name)
    run("git", "push", "origin", f"refs/tags/{name}")
    print(f"Pushed {name}; the GitHub Packages workflow builds and publishes it")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "tag", "resolve"])
    parser.add_argument("package", help="sdk-python, sdk-typescript, cli, or a tag for resolve")
    parser.add_argument("--out", type=Path, default=ROOT / "dist/release")
    args = parser.parse_args()
    if args.action == "resolve":
        print(package_for_tag(args.package))
        return
    if args.package not in PACKAGES:
        parser.error(f"unknown package: {args.package}")
    if args.action == "build":
        build(args.package, args.out)
    else:
        tag(args.package)


if __name__ == "__main__":
    main()
