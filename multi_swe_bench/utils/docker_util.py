# Copyright (c) 2024 Bytedance Ltd. and/or its affiliates

#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at

#      http://www.apache.org/licenses/LICENSE-2.0

#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import logging
from pathlib import Path
from typing import Optional, Union

import docker

docker_client = docker.from_env()


def exists(image_name: str) -> bool:
    try:
        docker_client.images.get(image_name)
        return True
    except docker.errors.ImageNotFound:
        return False


def cleanup_orphaned_containers(image_pattern: str = None, max_age_hours: int = 1) -> int:
    """
    Clean up orphaned containers that may have been left behind.
    
    Args:
        image_pattern: Optional pattern to match image names (e.g., "alibaba_m_sentinel")
        max_age_hours: Only clean up containers older than this many hours
    
    Returns:
        Number of containers cleaned up
    """
    import time
    from datetime import datetime, timezone
    
    logger = logging.getLogger(__name__)
    cleaned_count = 0
    
    try:
        # Get all containers (including stopped ones)
        all_containers = docker_client.containers.list(all=True)
        current_time = datetime.now(timezone.utc)
        
        for container in all_containers:
            try:
                # Check if container matches our pattern
                if image_pattern:
                    if not any(image_pattern.lower() in tag.lower() 
                             for tag in container.image.tags if tag):
                        continue
                
                # Check container age
                created_time = datetime.fromisoformat(container.attrs['Created'].replace('Z', '+00:00'))
                age_hours = (current_time - created_time).total_seconds() / 3600
                
                if age_hours < max_age_hours:
                    continue
                
                # Clean up the container
                container_id = container.short_id
                image_name = container.image.tags[0] if container.image.tags else "unknown"
                
                if container.status == 'running':
                    logger.info(f"Stopping orphaned container: {container_id} ({image_name})")
                    container.stop(timeout=10)
                
                logger.info(f"Removing orphaned container: {container_id} ({image_name})")
                container.remove(force=True)
                cleaned_count += 1
                
            except Exception as e:
                logger.warning(f"Failed to clean up container {container.short_id}: {e}")
                continue
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} orphaned containers")
        
        return cleaned_count
        
    except Exception as e:
        logger.error(f"Error during orphaned container cleanup: {e}")
        return 0


def build(
    workdir: Path, dockerfile_name: str, image_full_name: str, logger: logging.Logger
):
    workdir = str(workdir)
    logger.info(
        f"Start building image `{image_full_name}`, working directory is `{workdir}`"
    )
    try:
        build_logs = docker_client.api.build(
            path=workdir,
            dockerfile=dockerfile_name,
            tag=image_full_name,
            rm=True,
            forcerm=True,
            decode=True,
            encoding="utf-8",
        )

        for log in build_logs:
            if "stream" in log:
                logger.info(log["stream"].strip())
            elif "error" in log:
                error_message = log["error"].strip()
                logger.error(f"Docker build error: {error_message}")
                raise RuntimeError(f"Docker build failed: {error_message}")
            elif "status" in log:
                logger.info(log["status"].strip())
            elif "aux" in log:
                logger.info(log["aux"].get("ID", "").strip())

        logger.info(f"image({workdir}) build success: {image_full_name}")
    except docker.errors.BuildError as e:
        logger.error(f"build error: {e}")
        raise e
    except Exception as e:
        logger.error(f"Unknown build error occurred: {e}")
        raise e


def run(
    image_full_name: str,
    run_command: str,
    output_path: Optional[Path] = None,
    global_env: Optional[list[str]] = None,
    volumes: Optional[Union[dict[str, str], list[str]]] = None,
    timeout: Optional[int] = None,
) -> str:
    container = None
    try:
        container = docker_client.containers.run(
            image=image_full_name,
            command=run_command,
            remove=False,
            detach=True,
            stdout=True,
            stderr=True,
            environment=global_env,
            volumes=volumes,
        )

        output = ""
        try:
            if output_path:
                with open(output_path, "w", encoding="utf-8") as f:
                    # Wait for container with timeout
                    result = container.wait(timeout=timeout)
                    # Get logs after completion
                    output = container.logs().decode("utf-8")
                    f.write(output)
            else:
                # Wait for container with timeout
                result = container.wait(timeout=timeout)
                output = container.logs().decode("utf-8")
        except Exception as e:
            # Handle timeout or other errors
            if "timeout" in str(e).lower() or "timed out" in str(e).lower() or isinstance(e, TimeoutError):
                # Kill the container if it's still running
                try:
                    container.kill()
                    logging.getLogger(__name__).warning(f"Container killed due to timeout ({timeout}s): {image_full_name}")
                except:
                    pass
                raise TimeoutError(f"Container execution timed out after {timeout} seconds")
            else:
                raise e

        return output
    finally:
        if container:
            try:
                # First try to stop the container gracefully
                try:
                    container.stop(timeout=10)
                    logging.getLogger(__name__).debug(f"Container stopped: {container.short_id}")
                except Exception as stop_e:
                    # If graceful stop fails, try to kill it
                    try:
                        container.kill()
                        logging.getLogger(__name__).debug(f"Container killed: {container.short_id}")
                    except Exception as kill_e:
                        logging.getLogger(__name__).warning(f"Failed to stop/kill container {container.short_id}: {kill_e}")
                
                # Now remove the container
                container.remove(force=True)
                logging.getLogger(__name__).debug(f"Container removed: {container.short_id}")
                
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to cleanup container: {e}")
                # Try one more time with force removal
                try:
                    container.remove(force=True)
                    logging.getLogger(__name__).debug(f"Container force-removed on retry")
                except Exception as retry_e:
                    logging.getLogger(__name__).error(f"Final container cleanup failed: {retry_e}")
