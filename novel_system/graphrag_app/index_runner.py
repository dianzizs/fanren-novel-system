"""Run GraphRAG indexing via CLI subprocess."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .paths import graphrag_root
from ..config import AppConfig

logger = logging.getLogger(__name__)


class GraphRAGIndexRunner:
    """Execute GraphRAG index command via subprocess."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def run(self, book_id: str, force: bool = False) -> dict:
        root = graphrag_root(self._config, book_id)
        root_abs = str(root.resolve())

        env = os.environ.copy()
        env.setdefault("MINIMAX_API_KEY", self._config.minimax_api_key)

        cmd = [self._config.graphrag_python_executable, "index", "--root", root_abs]
        logger.info("Running GraphRAG index: %s", cmd)

        try:
            result = subprocess.run(
                cmd,
                env=env,
                timeout=self._config.graphrag_index_timeout_sec,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(root_abs),
            )
            logger.info("GraphRAG index stdout:\n%s", result.stdout[-2000:] if result.stdout else "(empty)")
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired as e:
            logger.error("GraphRAG index timed out after %d sec", self._config.graphrag_index_timeout_sec)
            return {
                "success": False,
                "error": f"Timeout after {self._config.graphrag_index_timeout_sec}s",
                "stdout": e.stdout or "",
                "stderr": e.stderr or "",
            }
        except subprocess.CalledProcessError as e:
            logger.error("GraphRAG index failed with code %d: %s", e.returncode, e.stderr[-1000:] if e.stderr else "")
            return {
                "success": False,
                "error": f"Exit code {e.returncode}",
                "stdout": e.stdout or "",
                "stderr": e.stderr or "",
            }
        except FileNotFoundError:
            logger.warning("graphrag CLI not found, trying python -m graphrag")
            fallback_cmd = [sys.executable, "-m", "graphrag", "index", "--root", root_abs]
            try:
                result = subprocess.run(
                    fallback_cmd,
                    env=env,
                    timeout=self._config.graphrag_index_timeout_sec,
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(root_abs),
                )
                return {
                    "success": True,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            except Exception as e2:
                logger.exception("GraphRAG index fallback also failed")
                return {"success": False, "error": str(e2)}
