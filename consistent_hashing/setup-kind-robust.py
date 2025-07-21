#!/usr/bin/env python3
"""
Robust Kind Cluster Setup for Consistent Hashing System

This script provides a more reliable way to set up Kind clusters with:
- Retry logic for failed cluster creation
- Fallback configurations (single-node -> multi-node)
- Resource optimization
- Better error diagnostics
- Automatic cleanup and recovery
"""

import sys
import os
import time
import subprocess
import argparse
import tempfile
from typing import Dict, List, Optional, Tuple, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class KindClusterManager:
    """Manages Kind cluster creation with robust error handling and fallbacks"""
    
    def __init__(self, cluster_name: str = "consistent-hashing-test", 
                 kubectl_timeout: int = 600, max_retries: int = 3):
        """
        Initialize the Kind cluster manager
        
        Args:
            cluster_name: Name of the Kind cluster
            kubectl_timeout: Timeout for kubectl operations in seconds
            max_retries: Maximum number of retry attempts
        """
        self.cluster_name = cluster_name
        self.kubectl_timeout = kubectl_timeout
        self.max_retries = max_retries
        self.cluster_context = f"kind-{cluster_name}"
        
        # Store original KUBECONFIG for restoration
        self.original_kubeconfig = os.environ.get('KUBECONFIG')
        self.k3s_kubeconfig_backup = None
        
        # Cluster configurations (from simple to complex)
        self.configurations = [
            self._get_single_node_config(),
            self._get_minimal_multi_node_config(),
            self._get_full_multi_node_config()
        ]
    
    def _run_command(self, cmd: List[str], timeout: Optional[int] = None, 
                    check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a command with proper error handling"""
        try:
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, 
                timeout=timeout,
                check=check,
                capture_output=capture_output,
                text=True
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"Exit code: {e.returncode}")
            if e.stdout:
                logger.error(f"Stdout: {e.stdout}")
            if e.stderr:
                logger.error(f"Stderr: {e.stderr}")
            raise
        except subprocess.TimeoutExpired as e:
            logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
            raise
    
    def _check_dependencies(self) -> None:
        """Check if required tools are available"""
        required_tools = ['kind', 'kubectl', 'docker']
        missing_tools: List[str] = []
        
        for tool in required_tools:
            try:
                self._run_command(['which', tool], check=True)
            except subprocess.CalledProcessError:
                missing_tools.append(tool)
        
        if missing_tools:
            raise RuntimeError(f"Missing required tools: {', '.join(missing_tools)}")
        
        # Check Docker is running
        try:
            self._run_command(['docker', 'info'], timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise RuntimeError("Docker is not running or accessible")
    
    def _setup_kubeconfig(self) -> None:
        """Setup kubeconfig to avoid conflicts with K3s and other clusters"""
        current_kubeconfig = os.environ.get('KUBECONFIG')
        
        if current_kubeconfig and 'k3s' in current_kubeconfig.lower():
            logger.warning("Detected K3s KUBECONFIG conflict. Temporarily unsetting KUBECONFIG for Kind...")
            self.k3s_kubeconfig_backup = current_kubeconfig
            del os.environ['KUBECONFIG']
            logger.info("KUBECONFIG temporarily unset to allow Kind to use default config")
        elif current_kubeconfig:
            logger.info(f"Using existing KUBECONFIG: {current_kubeconfig}")
        else:
            logger.info("Using default kubeconfig location: ~/.kube/config")
    
    def _restore_kubeconfig(self) -> None:
        """Restore original kubeconfig if it was backed up"""
        if self.k3s_kubeconfig_backup:
            logger.info("Restoring K3s KUBECONFIG...")
            os.environ['KUBECONFIG'] = self.k3s_kubeconfig_backup
            self.k3s_kubeconfig_backup = None
        elif self.original_kubeconfig and 'KUBECONFIG' not in os.environ:
            # Restore original if we unset it
            os.environ['KUBECONFIG'] = self.original_kubeconfig
    
    def _verify_context_exists(self) -> bool:
        """Verify that the expected kubectl context exists"""
        try:
            result = self._run_command(['kubectl', 'config', 'get-contexts', '-o', 'name'], check=False)
            contexts = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            if self.cluster_context in contexts:
                logger.debug(f"Context '{self.cluster_context}' found")
                return True
            else:
                logger.warning(f"Context '{self.cluster_context}' not found in kubeconfig")
                logger.warning(f"Available contexts: {contexts}")
                return False
        except Exception as e:
            logger.error(f"Failed to check kubectl contexts: {e}")
            return False
    
    def _get_single_node_config(self) -> Dict[str, Any]:
        """Get single-node cluster configuration (most reliable)"""
        return {
            "name": "single-node",
            "description": "Single control-plane node (most reliable)",
            "config": {
                "kind": "Cluster",
                "apiVersion": "kind.x-k8s.io/v1alpha4",
                "name": self.cluster_name,
                "nodes": [
                    {
                        "role": "control-plane",
                        "kubeadmConfigPatches": [
                            """kind: InitConfiguration
nodeRegistration:
  kubeletExtraArgs:
    node-labels: "ingress-ready=true"
    eviction-hard: "memory.available<100Mi,nodefs.available<1Gi"
    eviction-minimum-reclaim: "memory.available=0Mi,nodefs.available=500Mi"
"""
                        ],
                        "extraPortMappings": [
                            {"containerPort": 30000, "hostPort": 30000, "protocol": "TCP"},
                            {"containerPort": 32000, "hostPort": 32000, "protocol": "TCP"}
                        ]
                    }
                ]
            }
        }
    
    def _get_minimal_multi_node_config(self) -> Dict[str, Any]:
        """Get minimal multi-node configuration"""
        return {
            "name": "minimal-multi-node", 
            "description": "Control-plane + 1 worker (balanced reliability/functionality)",
            "config": {
                "kind": "Cluster",
                "apiVersion": "kind.x-k8s.io/v1alpha4",
                "name": self.cluster_name,
                "nodes": [
                    {
                        "role": "control-plane",
                        "kubeadmConfigPatches": [
                            """kind: InitConfiguration
nodeRegistration:
  kubeletExtraArgs:
    node-labels: "ingress-ready=true"
    eviction-hard: "memory.available<100Mi,nodefs.available<1Gi"
"""
                        ],
                        "extraPortMappings": [
                            {"containerPort": 30000, "hostPort": 30000, "protocol": "TCP"},
                            {"containerPort": 32000, "hostPort": 32000, "protocol": "TCP"}
                        ]
                    },
                    {
                        "role": "worker",
                        "kubeadmConfigPatches": [
                            """kind: JoinConfiguration
nodeRegistration:
  kubeletExtraArgs:
    eviction-hard: "memory.available<100Mi,nodefs.available<1Gi"
"""
                        ]
                    }
                ]
            }
        }
    
    def _get_full_multi_node_config(self) -> Dict[str, Any]:
        """Get full multi-node configuration (original)"""
        return {
            "name": "full-multi-node",
            "description": "Control-plane + 2 workers (maximum functionality)",
            "config": {
                "kind": "Cluster", 
                "apiVersion": "kind.x-k8s.io/v1alpha4",
                "name": self.cluster_name,
                "nodes": [
                    {
                        "role": "control-plane",
                        "kubeadmConfigPatches": [
                            """kind: InitConfiguration
nodeRegistration:
  kubeletExtraArgs:
    node-labels: "ingress-ready=true"
"""
                        ],
                        "extraPortMappings": [
                            {"containerPort": 30000, "hostPort": 30000, "protocol": "TCP"},
                            {"containerPort": 32000, "hostPort": 32000, "protocol": "TCP"}
                        ]
                    },
                    {"role": "worker"},
                    {"role": "worker"}
                ]
            }
        }
    
    def _cleanup_existing_cluster(self) -> bool:
        """Clean up existing cluster if it exists"""
        try:
            # Check if cluster exists
            result = self._run_command(['kind', 'get', 'clusters'], check=False)
            if self.cluster_name in result.stdout:
                logger.info(f"Deleting existing cluster '{self.cluster_name}'...")
                self._run_command(['kind', 'delete', 'cluster', '--name', self.cluster_name], timeout=120)
                logger.info("Existing cluster deleted")
                return True
            return False
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
            return False
    
    def _create_cluster_with_config(self, config: Dict[str, Any], node_image: str) -> Tuple[bool, str]:
        """Create cluster with specific configuration"""
        logger.info(f"Attempting cluster creation: {config['description']}")
        
        # Add node image to config
        cluster_config = config["config"].copy()
        for node in cluster_config["nodes"]:
            node["image"] = node_image
        
        try:
            # Write config to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                import yaml
                yaml.safe_dump(cluster_config, f)
                config_file = f.name
            
            try:
                # Create cluster
                cmd = ['kind', 'create', 'cluster', '--config', config_file]
                self._run_command(cmd, timeout=600)
                
                # Wait for cluster to be ready
                logger.info("Waiting for cluster to be ready...")
                self._run_command([
                    'kubectl', 'cluster-info', 
                    '--context', self.cluster_context
                ], timeout=60)
                
                # Wait for all nodes to be ready
                self._run_command([
                    'kubectl', 'wait', '--for=condition=Ready', 'nodes', '--all',
                    '--timeout=300s', '--context', self.cluster_context
                ], timeout=320)
                
                logger.info(f"✅ Cluster created successfully with {config['name']} configuration")
                return True, config['name']
                
            finally:
                # Clean up config file
                os.unlink(config_file)
                
        except Exception as e:
            logger.error(f"Failed to create cluster with {config['name']} configuration: {e}")
            return False, str(e)
    
    def _diagnose_cluster_issues(self) -> None:
        """Diagnose common cluster issues"""
        logger.info("Diagnosing cluster issues...")
        
        try:
            # Check Docker resources
            result = self._run_command(['docker', 'system', 'df'], check=False)
            logger.info(f"Docker disk usage:\n{result.stdout}")
            
            # Check Docker containers
            result = self._run_command(['docker', 'ps', '-a', '--filter', f'name={self.cluster_name}'], check=False)
            logger.info(f"Docker containers for cluster:\n{result.stdout}")
            
            # Check system resources
            result = self._run_command(['free', '-h'], check=False)
            logger.info(f"Memory usage:\n{result.stdout}")
            
            # Check for conflicting kubeconfig
            kubeconfig = os.environ.get('KUBECONFIG', '~/.kube/config')
            logger.info(f"KUBECONFIG: {kubeconfig}")
            
        except Exception as e:
            logger.warning(f"Error during diagnosis: {e}")
    
    def create_cluster(self, node_image: str = "kindest/node:v1.28.0", 
                      force_config: Optional[str] = None) -> bool:
        """
        Create Kind cluster with robust retry and fallback logic
        
        Args:
            node_image: Docker image for Kubernetes nodes
            force_config: Force specific configuration (single-node, minimal-multi-node, full-multi-node)
            
        Returns:
            bool: True if cluster was created successfully
        """
        logger.info(f"Creating Kind cluster '{self.cluster_name}' with image '{node_image}'")
        
        # Check dependencies
        self._check_dependencies()
        
        # Setup kubeconfig to avoid conflicts
        self._setup_kubeconfig()
        
        try:
            # Clean up existing cluster
            self._cleanup_existing_cluster()
            
            # Determine configurations to try
            configs_to_try = self.configurations
            if force_config:
                configs_to_try = [c for c in self.configurations if c['name'] == force_config]
                if not configs_to_try:
                    raise ValueError(f"Unknown configuration: {force_config}")
            
            # Try each configuration with retries
            for attempt in range(self.max_retries):
                logger.info(f"=== Attempt {attempt + 1}/{self.max_retries} ===")
                
                for config in configs_to_try:
                    try:
                        success, result = self._create_cluster_with_config(config, node_image)
                        if success:
                            logger.info(f"🎉 Cluster '{self.cluster_name}' created successfully!")
                            logger.info(f"Configuration used: {result}")
                            self._show_cluster_info()
                            return True
                    except Exception as e:
                        logger.error(f"Configuration {config['name']} failed: {e}")
                        continue
                
                # If we get here, all configurations failed for this attempt
                if attempt < self.max_retries - 1:
                    logger.warning(f"All configurations failed on attempt {attempt + 1}. Retrying in 10 seconds...")
                    time.sleep(10)
                    self._cleanup_existing_cluster()  # Clean up before retry
            
            # All attempts failed
            logger.error("❌ All cluster creation attempts failed!")
            self._diagnose_cluster_issues()
            return False
        
        finally:
            # Always restore kubeconfig
            self._restore_kubeconfig()
    
    def _show_cluster_info(self) -> None:
        """Show cluster information"""
        try:
            logger.info("Cluster information:")
            
            # Check if context exists
            use_context = self._verify_context_exists()
            
            # Node information
            cmd = ['kubectl', 'get', 'nodes', '-o', 'wide']
            if use_context:
                cmd.extend(['--context', self.cluster_context])
            result = self._run_command(cmd, check=False)
            logger.info(f"Nodes:\n{result.stdout}")
            
            # Cluster info
            cmd = ['kubectl', 'cluster-info']
            if use_context:
                cmd.extend(['--context', self.cluster_context])
            result = self._run_command(cmd, check=False)
            logger.info(f"Cluster info:\n{result.stdout}")
            
        except Exception as e:
            logger.warning(f"Could not retrieve cluster info: {e}")
    
    def delete_cluster(self) -> bool:
        """Delete the Kind cluster"""
        # Setup kubeconfig to avoid conflicts
        self._setup_kubeconfig()
        
        try:
            logger.info(f"Deleting cluster '{self.cluster_name}'...")
            self._run_command(['kind', 'delete', 'cluster', '--name', self.cluster_name], timeout=120)
            logger.info("✅ Cluster deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to delete cluster: {e}")
            return False
        finally:
            # Always restore kubeconfig
            self._restore_kubeconfig()
    
    def quick_health_check(self) -> bool:
        """Quick health check without creating test pods"""
        try:
            logger.info("Running quick cluster health check...")
            
            # Check if context exists
            use_context = self._verify_context_exists()
            
            # Test basic kubectl access
            cmd = ['kubectl', 'get', 'nodes']
            if use_context:
                cmd.extend(['--context', self.cluster_context])
            result = self._run_command(cmd, timeout=15)
            
            # Check if nodes are ready
            if 'Ready' in result.stdout:
                logger.info("✅ Quick health check passed - cluster is accessible and nodes are ready")
                return True
            else:
                logger.warning("⚠️ Cluster is accessible but nodes may not be ready")
                return False
                
        except Exception as e:
            logger.error(f"❌ Quick health check failed: {e}")
            return False
    
    def verify_cluster(self) -> bool:
        """Verify cluster is working properly"""
        try:
            logger.info("Verifying cluster functionality...")
            
            # First verify that the context exists
            if not self._verify_context_exists():
                logger.error(f"Cluster context '{self.cluster_context}' not found in kubeconfig")
                logger.error("This usually means Kind failed to update the kubeconfig properly")
                
                # Try without context as fallback
                logger.info("Trying kubectl without explicit context...")
                try:
                    self._run_command(['kubectl', 'get', 'nodes'], timeout=30)
                    logger.warning("kubectl works without context - using default context")
                    use_context = False
                except Exception:
                    logger.error("kubectl doesn't work even without context")
                    return False
            else:
                use_context = True
            
            # Test basic kubectl access
            cmd = ['kubectl', 'get', 'nodes']
            if use_context:
                cmd.extend(['--context', self.cluster_context])
            self._run_command(cmd, timeout=30)
            
            # Test creating a test pod
            test_yaml = """
apiVersion: v1
kind: Pod
metadata:
  name: cluster-test
  namespace: default
spec:
  containers:
  - name: test
    image: busybox:1.35
    command: ['sleep', '60']
  restartPolicy: Never
"""
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(test_yaml)
                test_file = f.name
            
            try:
                # Create test pod
                cmd = ['kubectl', 'apply', '-f', test_file]
                if use_context:
                    cmd.extend(['--context', self.cluster_context])
                self._run_command(cmd, timeout=30)
                
                # Wait for pod to be ready
                cmd = ['kubectl', 'wait', '--for=condition=Ready', 'pod/cluster-test', '--timeout=60s']
                if use_context:
                    cmd.extend(['--context', self.cluster_context])
                self._run_command(cmd, timeout=70)
                
                logger.info("✅ Cluster verification successful")
                verification_success = True
                
            except Exception as e:
                logger.error(f"Cluster verification failed: {e}")
                verification_success = False
                
            finally:
                # Always try to clean up test pod, but don't fail verification if cleanup fails
                try:
                    cmd = ['kubectl', 'delete', 'pod', 'cluster-test', '--ignore-not-found']
                    if use_context:
                        cmd.extend(['--context', self.cluster_context])
                    self._run_command(cmd, timeout=30, check=False)
                except subprocess.TimeoutExpired:
                    logger.warning("Pod cleanup timed out, trying force delete...")
                    try:
                        cmd = ['kubectl', 'delete', 'pod', 'cluster-test', '--force', '--grace-period=0', '--ignore-not-found']
                        if use_context:
                            cmd.extend(['--context', self.cluster_context])
                        self._run_command(cmd, timeout=15, check=False)
                    except Exception:
                        logger.warning("Force delete also failed, but continuing anyway...")
                except Exception:
                    logger.warning("Pod cleanup failed, but continuing anyway...")
                
                # Clean up temp file
                os.unlink(test_file)
                
            return verification_success
                
        except Exception as e:
            logger.error(f"Cluster verification failed: {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Robust Kind Cluster Setup")
    
    parser.add_argument("--cluster-name", default="consistent-hashing-test",
                       help="Name of the Kind cluster")
    parser.add_argument("--node-image", default="kindest/node:v1.28.0",
                       help="Kubernetes node image")
    parser.add_argument("--max-retries", type=int, default=3,
                       help="Maximum retry attempts")
    parser.add_argument("--timeout", type=int, default=600,
                       help="Kubectl operation timeout in seconds")
    
    # Actions
    parser.add_argument("--create", action="store_true",
                       help="Create the cluster")
    parser.add_argument("--delete", action="store_true", 
                       help="Delete the cluster")
    parser.add_argument("--verify", action="store_true",
                       help="Verify cluster functionality (full test with pod creation)")
    parser.add_argument("--quick-check", action="store_true",
                       help="Quick health check (just node status, no pod creation)")
    
    # Configuration options
    parser.add_argument("--config", choices=["single-node", "minimal-multi-node", "full-multi-node"],
                       help="Force specific cluster configuration")
    
    # Logging
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    parser.add_argument("--quiet", "-q", action="store_true",
                       help="Suppress info logging")
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Import yaml here to catch import errors early
    try:
        import yaml
    except ImportError:
        logger.error("PyYAML is required but not installed. Install with: pip install pyyaml")
        sys.exit(1)
    
    # Create cluster manager
    manager = KindClusterManager(
        cluster_name=args.cluster_name,
        kubectl_timeout=args.timeout,
        max_retries=args.max_retries
    )
    
    try:
        success = True
        
        if args.delete:
            success = manager.delete_cluster()
        elif args.verify:
            success = manager.verify_cluster()
        elif args.quick_check:
            success = manager.quick_health_check()
        elif args.create:
            success = manager.create_cluster(
                node_image=args.node_image,
                force_config=args.config
            )
            if success and not args.quiet:
                # Use quick check by default, full verify only if explicitly requested
                success = manager.quick_health_check()
        else:
            # Default action: create cluster
            success = manager.create_cluster(
                node_image=args.node_image,
                force_config=args.config
            )
            if success and not args.quiet:
                # Use quick check by default, full verify only if explicitly requested
                success = manager.quick_health_check()
        
        if success:
            logger.info("🎉 Operation completed successfully!")
            sys.exit(0)
        else:
            logger.error("💥 Operation failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 