"""
Remote Executor MCP Server
Handles SSH-based execution on Lambda Labs GPU instances
"""

import paramiko
import os
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import time

logger = logging.getLogger(__name__)

class RemoteExecutor:
    """
    Handles remote execution of RadonPy commands on Lambda Labs via SSH.
    """
    
    def __init__(
        self,
        host: str,
        username: str,
        key_path: str,
        remote_workdir: str = "/home/arz2/simulations",
        conda_env: str = "radonpy",
        port: int = 22
    ):
        self.host = host
        self.username = username
        self.key_path = os.path.expanduser(key_path)
        self.remote_workdir = remote_workdir
        self.conda_env = conda_env
        self.port = port
        
        self.ssh_client = None
        self.sftp_client = None
        
        logger.info(f"RemoteExecutor initialized for {username}@{host}")
    
    def _is_connected(self) -> bool:
        """Check if the SSH transport is alive."""
        try:
            transport = self.ssh_client.get_transport() if self.ssh_client else None
            return transport is not None and transport.is_active()
        except Exception:
            return False

    def _ensure_connected(self, max_retries: int = 3, retry_delay: float = 5.0):
        """Reconnect if the SSH connection is stale or dead, with retries."""
        if self._is_connected():
            return

        logger.warning("SSH connection is stale or dead — reconnecting...")
        try:
            if self.sftp_client:
                self.sftp_client.close()
            if self.ssh_client:
                self.ssh_client.close()
        except Exception:
            pass
        self.ssh_client = None
        self.sftp_client = None

        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Reconnect attempt {attempt}/{max_retries}...")
                self.connect()
                return
            except Exception as e:
                last_err = e
                logger.warning(f"Reconnect attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(retry_delay)

        raise ConnectionError(
            f"Failed to reconnect to {self.host} after {max_retries} attempts: {last_err}"
        )

    def connect(self):
        """Establish SSH connection to Lambda."""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh_client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                key_filename=self.key_path,
                timeout=60,
                banner_timeout=30
            )
            
            self.sftp_client = self.ssh_client.open_sftp()
            logger.info("SSH connection established")
            
            # Ensure remote workdir exists
            self._ensure_workdir()
            
        except Exception as e:
            logger.error(f"Failed to connect to Lambda: {e}")
            raise
    
    def _ensure_workdir(self):
        """Ensure remote working directory exists."""
        try:
            self.sftp_client.stat(self.remote_workdir)
        except IOError:
            # Directory doesn't exist, create it
            stdin, stdout, stderr = self.ssh_client.exec_command(f"mkdir -p {self.remote_workdir}")
            stdout.channel.recv_exit_status()
            logger.info(f"Created remote workdir: {self.remote_workdir}")
    
    def disconnect(self):
        """Close SSH connection."""
        if self.sftp_client:
            self.sftp_client.close()
        if self.ssh_client:
            self.ssh_client.close()
        logger.info("SSH connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    def execute_command(
        self,
        command: str,
        workdir: Optional[str] = None,
        timeout: int = 3600,
        env_vars: Optional[dict] = None
    ) -> Tuple[str, str, int]:
        """
        Execute command on remote Lambda instance.
        
        Args:
            command: Command to execute
            workdir: Working directory (defaults to remote_workdir)
            timeout: Command timeout in seconds
            env_vars: Optional environment variables dict (e.g., {'CUDA_VISIBLE_DEVICES': '2,3'})
            
        Returns:
            (stdout, stderr, exit_code)
        """
        self._ensure_connected()
        
        workdir = workdir or self.remote_workdir
        
        # Default environment variables
        default_env = {
            'DISPLAY': '',
            'NVIDIA_DRIVER_CAPABILITIES': 'compute,utility',
            'CUDA_VISIBLE_DEVICES': '0,1,2,3'
        }
        
        # Merge with custom env vars (custom takes precedence)
        if env_vars:
            default_env.update(env_vars)
        
        # Build export statements
        env_exports = '\n'.join([f"export {k}={v}" for k, v in default_env.items()])
        
        # Wrap command with conda activation and cd to workdir
        full_command = f"""
            {env_exports}
            source ~/miniforge3/etc/profile.d/conda.sh
            conda activate {self.conda_env}
            cd {workdir}
            {command}
            """
        
        logger.info(f"Executing remote command: {command}")
        logger.debug(f"Environment: {default_env}")
        
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(
                full_command,
                timeout=timeout,
                get_pty=False  # For interactive output
            )
            
            # Read output
            stdout_str = stdout.read().decode('utf-8', errors='ignore')
            stderr_str = stderr.read().decode('utf-8', errors='ignore')
            exit_code = stdout.channel.recv_exit_status()
            
            if exit_code != 0:
                logger.warning(f"Command failed with exit code {exit_code}")
                logger.warning(f"stderr: {stderr_str}")
            else:
                logger.info("Command completed successfully")
            
            return stdout_str, stderr_str, exit_code
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise

    
    def execute_python_script(
        self,
        script: str,
        workdir: Optional[str] = None,
        timeout: int = 36000,
        env_vars: Optional[dict] = None
    ) -> Tuple[str, str, int]:
        """
        Execute Python script on remote instance.
        
        Args:
            script: Python code to execute
            workdir: Working directory
            timeout: Timeout in seconds
            env_vars: Optional environment variables dict
            
        Returns:
            (stdout, stderr, exit_code)
        """
        # Escape quotes in script
        script_escaped = script.replace('"', '\\"').replace('$', '\\$')
        
        command = f'python -c "{script_escaped}"'
        
        return self.execute_command(command, workdir, timeout, env_vars)
        
    def upload_file(
        self,
        local_path: str,
        remote_path: str
    ):
        """
        Upload file to remote instance.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path
        """
        self._ensure_connected()
        
        try:
            # Ensure remote directory exists
            remote_dir = os.path.dirname(remote_path)
            self.execute_command(f"mkdir -p {remote_dir}")
            
            logger.info(f"Uploading {local_path} -> {remote_path}")
            self.sftp_client.put(local_path, remote_path)
            logger.info("Upload complete")
            
        except Exception as e:
            logger.error(f"File upload failed: {e}")
            raise
    
    def download_file(
        self,
        remote_path: str,
        local_path: str
    ):
        """
        Download file from remote instance.
        
        Args:
            remote_path: Remote file path
            local_path: Local file path
        """
        self._ensure_connected()
        
        try:
            # Ensure local directory exists
            local_dir = os.path.dirname(local_path)
            os.makedirs(local_dir, exist_ok=True)
            
            logger.info(f"Downloading {remote_path} -> {local_path}")
            self.sftp_client.get(remote_path, local_path)
            logger.info("Download complete")
            
        except Exception as e:
            logger.error(f"File download failed: {e}")
            raise
    
    def file_exists(self, remote_path: str) -> bool:
        """Check if file exists on remote."""
        self._ensure_connected()
        
        try:
            self.sftp_client.stat(remote_path)
            return True
        except IOError:
            return False
    
    def read_file(self, remote_path: str) -> str:
        """Read file content from remote."""
        self._ensure_connected()
        
        try:
            with self.sftp_client.open(remote_path, 'rb') as f:
                content = f.read()
                return content.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to read file {remote_path}: {e}")
            raise
    
    def write_file(self, content: str, remote_path: str):
        """Write content to remote file."""
        self._ensure_connected()
        
        try:
            # Ensure remote directory exists
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                self.execute_command(f"mkdir -p {remote_dir}")
            
            with self.sftp_client.open(remote_path, 'wb') as f:
                if isinstance(content, str):
                    f.write(content.encode('utf-8'))
                else:
                    f.write(content)
            logger.info(f"Wrote to {remote_path}")
            
        except Exception as e:
            logger.error(f"Failed to write file {remote_path}: {e}")
            raise
    
    def list_directory(self, remote_path: str) -> list:
        """List directory contents on remote."""
        self._ensure_connected()
        
        try:
            return self.sftp_client.listdir(remote_path)
        except Exception as e:
            logger.error(f"Failed to list directory {remote_path}: {e}")
            raise
    
    def submit_background_job(
        self,
        command: str,
        job_name: str,
        workdir: Optional[str] = None,
        log_file: Optional[str] = None
    ) -> str:
        """
        Submit a long-running job in the background.
        
        Args:
            command: Command to execute
            job_name: Unique job identifier
            workdir: Working directory
            log_file: Log file path (relative to workdir)
            
        Returns:
            job_id: Unique job ID for status checking
        """
        workdir = workdir or self.remote_workdir
        log_file = log_file or f"logs/{job_name}.log"
        
        # Create job script
        job_script = f"""#!/bin/bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate {self.conda_env}
cd {workdir}
{command}
"""
        
        job_script_path = f"{workdir}/jobs/{job_name}.sh"
        
        # Create jobs directory
        self.execute_command(f"mkdir -p {workdir}/jobs {workdir}/logs")
        
        # Write job script
        self.write_file(job_script, job_script_path)
        
        # Make executable
        self.execute_command(f"chmod +x {job_script_path}")
        
        # Submit job in background
        submit_cmd = f"nohup {job_script_path} > {workdir}/{log_file} 2>&1 & echo $!"
        stdout, stderr, exit_code = self.execute_command(submit_cmd, workdir)
        
        if exit_code != 0:
            raise RuntimeError(f"Failed to submit job: {stderr}")
        
        # Extract PID
        pid = stdout.strip().split()[-1]
        
        logger.info(f"Job {job_name} submitted with PID {pid}")
        
        return pid
    
    def check_job_status(self, job_id: str) -> str:
        """
        Check if a background job is still running.
        
        Args:
            job_id: Job ID (PID) returned from submit_background_job
            
        Returns:
            "running", "completed", or "failed"
        """
        stdout, stderr, exit_code = self.execute_command(f"ps -p {job_id}")
        
        if exit_code == 0 and job_id in stdout:
            return "running"
        else:
            return "completed"


# Singleton instance for connection pooling
_executor_instance = None

def get_remote_executor(
    host: str = os.environ.get("LAMBDA_HOST", "YOUR_SERVER_IP"),
    username: str = os.environ.get("LAMBDA_USER", "YOUR_USERNAME"),
    key_path: str = os.environ.get("LAMBDA_KEY", "~/.ssh/your_key"),
    remote_workdir: str = os.environ.get("LAMBDA_WORKDIR", "/home/YOUR_USERNAME/simulations"),
) -> RemoteExecutor:
    """Get or create RemoteExecutor singleton instance."""
    global _executor_instance
    
    if _executor_instance is None:
        _executor_instance = RemoteExecutor(
            host=host,
            username=username,
            key_path=key_path,
            remote_workdir=remote_workdir
        )
        _executor_instance.connect()
    
    return _executor_instance
