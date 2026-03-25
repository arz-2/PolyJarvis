#!/usr/bin/env python3
"""
PolyJarvis LAMMPS Engine — Remote Utility Tools
================================================
File/shell utilities for the remote simulation server.
Registered into the shared FastMCP instance via register(mcp, executor).

Tools:
  1.  list_remote_files            - List files in a remote directory
  2.  list_remote_files_detailed   - List files with size + mtime
  3.  upload_file_to_remote        - Upload a local file to remote server
  4.  download_file_from_remote    - Download a remote file locally
  5.  check_remote_status          - Check server status and GPU availability
  6.  read_remote_file             - Read full content of a remote file
  7.  read_remote_file_tail        - Read last N lines of a remote file
  8.  write_remote_file            - Write content to a remote file
  9.  execute_remote_shell_command - Run an arbitrary shell command remotely
  10. check_remote_file_exists     - Check whether a remote path exists
"""

import stat
import logging
from pathlib import Path

logger = logging.getLogger("lammps_engine")


def register(mcp, executor):
    """Register all utility tools onto the given FastMCP instance."""

    # ── 1. list_remote_files ─────────────────────────────────────────────────

    @mcp.tool()
    def list_remote_files(remote_dir: str = "/home/arz2/simulations") -> dict:
        """
        List files in a directory on the remote simulation server.

        Args:
            remote_dir: Directory path on the remote server.

        Returns:
            dict with files list and count.
        """
        try:
            files = executor.list_directory(remote_dir)
            return {
                "status":    "success",
                "directory": remote_dir,
                "files":     files,
                "count":     len(files),
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ── 2. list_remote_files_detailed ────────────────────────────────────────

    @mcp.tool()
    def list_remote_files_detailed(remote_dir: str) -> dict:
        """
        List files in a remote directory with size and modification time.

        Args:
            remote_dir: Directory path on the remote server.

        Returns:
            dict with detailed file listing (name, type, size_bytes, modified).
        """
        try:
            file_list = []
            for attr in executor.sftp_client.listdir_attr(remote_dir):
                file_list.append({
                    "name":       attr.filename,
                    "type":       "directory" if stat.S_ISDIR(attr.st_mode) else "file",
                    "size_bytes": attr.st_size,
                    "modified":   attr.st_mtime,
                })
            return {
                "status":    "success",
                "directory": remote_dir,
                "files":     file_list,
                "count":     len(file_list),
            }
        except Exception as e:
            logger.error(f"Failed to list {remote_dir}: {e}")
            return {"status": "error", "directory": remote_dir, "error": str(e)}

    # ── 3. upload_file_to_remote ─────────────────────────────────────────────

    @mcp.tool()
    def upload_file_to_remote(local_path: str, remote_path: str = None) -> dict:
        """
        Upload a file from the local machine to the remote simulation server.

        Args:
            local_path:  Local file path to upload.
            remote_path: Destination path on the remote server.
                         Defaults to /home/arz2/simulations/<filename>.

        Returns:
            dict with upload status and remote_path.
        """
        if remote_path is None:
            remote_path = f"/home/arz2/simulations/{Path(local_path).name}"
        try:
            executor.upload_file(local_path, remote_path)
            return {
                "status":      "success",
                "local_path":  local_path,
                "remote_path": remote_path,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ── 4. download_file_from_remote ─────────────────────────────────────────

    @mcp.tool()
    def download_file_from_remote(remote_path: str, local_path: str = None) -> dict:
        """
        Download a file from the remote simulation server to the local machine.

        Args:
            remote_path: File path on the remote server.
            local_path:  Local destination path.
                         Defaults to /tmp/<filename>.

        Returns:
            dict with local_path on success.
        """
        if local_path is None:
            local_path = f"/tmp/{Path(remote_path).name}"
        try:
            executor.download_file(remote_path, local_path)
            return {
                "status":      "success",
                "remote_path": remote_path,
                "local_path":  local_path,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ── 5. check_remote_status ───────────────────────────────────────────────

    @mcp.tool()
    def check_remote_status() -> dict:
        """
        Check remote server connectivity, hostname, and GPU availability.

        Returns:
            dict with host info, GPU list (name, total/used VRAM), and
            radonpy version.
        """
        stdout, _, rc = executor.execute_command("hostname")
        hostname = stdout.strip() if rc == 0 else "unknown"

        stdout, _, rc = executor.execute_command(
            "nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader"
        )
        gpus = []
        if rc == 0:
            for i, line in enumerate(stdout.strip().split("\n")):
                parts = line.split(",")
                if len(parts) == 3:
                    gpus.append({
                        "gpu_id":       i,
                        "name":         parts[0].strip(),
                        "memory_total": parts[1].strip(),
                        "memory_used":  parts[2].strip(),
                    })

        stdout, _, rc = executor.execute_python_script(
            "import radonpy; print(radonpy.__version__)"
        )
        radonpy_version = stdout.strip() if rc == 0 else "unknown"

        return {
            "status":          "connected",
            "remote_host":     executor.host,
            "hostname":        hostname,
            "remote_workdir":  executor.remote_workdir,
            "radonpy_version": radonpy_version,
            "gpu_count":       len(gpus),
            "gpus":            gpus,
        }

    # ── 6. read_remote_file ──────────────────────────────────────────────────

    @mcp.tool()
    def read_remote_file(remote_path: str) -> dict:
        """
        Read the full content of a file on the remote server.

        Args:
            remote_path: Full path to the file on the remote server
                         (e.g. '/home/arz2/simulations/run1/log.lammps').

        Returns:
            dict with content, size_bytes, and line count.
        """
        try:
            content = executor.read_file(remote_path)
            try:
                size_bytes = executor.sftp_client.stat(remote_path).st_size
            except Exception:
                size_bytes = len(content.encode("utf-8"))
            return {
                "status":     "success",
                "file":       remote_path,
                "content":    content,
                "size_bytes": size_bytes,
                "lines":      len(content.split("\n")),
            }
        except Exception as e:
            logger.error(f"Failed to read {remote_path}: {e}")
            return {"status": "error", "file": remote_path, "error": str(e)}

    # ── 7. read_remote_file_tail ─────────────────────────────────────────────

    @mcp.tool()
    def read_remote_file_tail(remote_path: str, n_lines: int = 50) -> dict:
        """
        Read the last N lines of a file on the remote server.
        Useful for monitoring live logs without transferring the whole file.

        Args:
            remote_path: Full path to the file on the remote server.
            n_lines:     Number of lines from the end to return (default: 50).

        Returns:
            dict with content (last n_lines), lines_returned, and total_lines.
        """
        try:
            content = executor.read_file(remote_path)
            lines   = content.split("\n")
            tail    = lines[-n_lines:] if len(lines) > n_lines else lines
            return {
                "status":         "success",
                "file":           remote_path,
                "content":        "\n".join(tail),
                "lines_returned": len(tail),
                "total_lines":    len(lines),
            }
        except Exception as e:
            logger.error(f"Failed to read tail of {remote_path}: {e}")
            return {"status": "error", "file": remote_path, "error": str(e)}

    # ── 8. write_remote_file ─────────────────────────────────────────────────

    @mcp.tool()
    def write_remote_file(remote_path: str, content: str) -> dict:
        """
        Write content to a file on the remote server (creates or overwrites).

        Args:
            remote_path: Full destination path on the remote server.
            content:     Text content to write.

        Returns:
            dict with bytes_written on success.
        """
        try:
            executor.write_file(content, remote_path)
            return {
                "status":        "success",
                "file":          remote_path,
                "bytes_written": len(content.encode("utf-8")),
            }
        except Exception as e:
            logger.error(f"Failed to write {remote_path}: {e}")
            return {"status": "error", "file": remote_path, "error": str(e)}

    # ── 9. execute_remote_shell_command ──────────────────────────────────────

    @mcp.tool()
    def execute_remote_shell_command(
        command: str,
        workdir: str = None,
        timeout: int = 60,
    ) -> dict:
        """
        Execute an arbitrary shell command on the remote simulation server.

        Args:
            command: Shell command string to run.
            workdir: Working directory (default: remote_workdir).
            timeout: Timeout in seconds (default: 60).

        Returns:
            dict with stdout, stderr, and exit_code.
        """
        try:
            stdout, stderr, exit_code = executor.execute_command(
                command, workdir=workdir, timeout=timeout
            )
            return {
                "status":    "success" if exit_code == 0 else "failed",
                "command":   command,
                "stdout":    stdout,
                "stderr":    stderr,
                "exit_code": exit_code,
            }
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {"status": "error", "command": command, "error": str(e)}

    # ── 10. check_remote_file_exists ─────────────────────────────────────────

    @mcp.tool()
    def check_remote_file_exists(remote_path: str) -> dict:
        """
        Check whether a path exists on the remote simulation server.

        Args:
            remote_path: Full path to check.

        Returns:
            dict with exists (bool).
        """
        return {
            "status": "success",
            "path":   remote_path,
            "exists": executor.file_exists(remote_path),
        }
