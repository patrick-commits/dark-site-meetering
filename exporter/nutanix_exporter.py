#!/usr/bin/env python3
"""
Nutanix Prism Central Prometheus Exporter

Exports metrics from Nutanix Prism Central v3 API for Prometheus scraping.
"""

import os
import time
import logging
import requests
from requests.auth import HTTPBasicAuth
from prometheus_client import start_http_server, Gauge, Info, Counter
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
NUTANIX_HOST = os.getenv('NUTANIX_HOST', 'prism-central.example.com')
NUTANIX_USERNAME = os.getenv('NUTANIX_USERNAME', 'admin')
NUTANIX_PASSWORD = os.getenv('NUTANIX_PASSWORD', 'changeme')
EXPORTER_PORT = int(os.getenv('EXPORTER_PORT', 9090))
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', 60))

# Base URL for Nutanix API
BASE_URL = f"https://{NUTANIX_HOST}:9440/api/nutanix"

# Prometheus metrics
# Cluster metrics
cluster_info = Info('nutanix_cluster', 'Nutanix cluster information')
cluster_cpu_usage = Gauge('nutanix_cluster_cpu_usage_percent', 'Cluster CPU usage percentage', ['cluster_name', 'cluster_uuid'])
cluster_memory_usage = Gauge('nutanix_cluster_memory_usage_percent', 'Cluster memory usage percentage', ['cluster_name', 'cluster_uuid'])
cluster_storage_usage = Gauge('nutanix_cluster_storage_usage_bytes', 'Cluster storage usage in bytes', ['cluster_name', 'cluster_uuid'])
cluster_storage_capacity = Gauge('nutanix_cluster_storage_capacity_bytes', 'Cluster storage capacity in bytes', ['cluster_name', 'cluster_uuid'])
cluster_storage_free = Gauge('nutanix_cluster_storage_free_bytes', 'Cluster storage free in bytes', ['cluster_name', 'cluster_uuid'])
cluster_node_count = Gauge('nutanix_cluster_node_count', 'Number of nodes in cluster', ['cluster_name', 'cluster_uuid'])
cluster_physical_cpu_cores = Gauge('nutanix_cluster_physical_cpu_cores', 'Total physical CPU cores in cluster', ['cluster_name', 'cluster_uuid'])

# License metrics
license_type = Info('nutanix_license', 'Nutanix license information')
license_cores = Gauge('nutanix_license_cores', 'Licensed CPU cores', ['cluster_name', 'license_type'])

# VM metrics
vm_count = Gauge('nutanix_vm_count', 'Total number of VMs', ['cluster_name'])
vm_power_state = Gauge('nutanix_vm_power_state', 'VM power state (1=ON, 0=OFF)', ['vm_name', 'vm_uuid', 'cluster_name'])
vm_cpu_count = Gauge('nutanix_vm_cpu_count', 'Number of vCPUs assigned to VM', ['vm_name', 'vm_uuid'])
vm_memory_bytes = Gauge('nutanix_vm_memory_bytes', 'Memory assigned to VM in bytes', ['vm_name', 'vm_uuid'])
vm_disk_size_bytes = Gauge('nutanix_vm_disk_size_bytes', 'Total disk size of VM in bytes', ['vm_name', 'vm_uuid'])

# Host metrics
host_count = Gauge('nutanix_host_count', 'Total number of hosts', ['cluster_name'])
host_cpu_usage = Gauge('nutanix_host_cpu_usage_percent', 'Host CPU usage percentage', ['host_name', 'host_uuid', 'cluster_name'])
host_memory_usage = Gauge('nutanix_host_memory_usage_percent', 'Host memory usage percentage', ['host_name', 'host_uuid', 'cluster_name'])
host_num_vms = Gauge('nutanix_host_num_vms', 'Number of VMs on host', ['host_name', 'host_uuid', 'cluster_name'])
host_physical_cpu_cores = Gauge('nutanix_host_physical_cpu_cores', 'Physical CPU cores on host', ['host_name', 'host_uuid', 'cluster_name'])
host_cpu_sockets = Gauge('nutanix_host_cpu_sockets', 'Number of CPU sockets on host', ['host_name', 'host_uuid', 'cluster_name'])

# Storage container metrics
storage_container_usage = Gauge('nutanix_storage_container_usage_bytes', 'Storage container usage in bytes', ['container_name', 'container_uuid'])
storage_container_capacity = Gauge('nutanix_storage_container_capacity_bytes', 'Storage container capacity in bytes', ['container_name', 'container_uuid'])

# File server metrics
file_server_capacity = Gauge('nutanix_file_server_capacity_bytes', 'File server storage capacity in bytes', ['file_server_name', 'file_server_uuid'])
file_server_used = Gauge('nutanix_file_server_used_bytes', 'File server storage used in bytes', ['file_server_name', 'file_server_uuid'])
file_server_available = Gauge('nutanix_file_server_available_bytes', 'File server storage available in bytes', ['file_server_name', 'file_server_uuid'])
file_server_files_count = Gauge('nutanix_file_server_files_count', 'Number of files on file server', ['file_server_name', 'file_server_uuid'])
file_server_connections = Gauge('nutanix_file_server_connections', 'Number of connections to file server', ['file_server_name', 'file_server_uuid'])

# API request metrics
api_requests_total = Counter('nutanix_exporter_api_requests_total', 'Total API requests made', ['endpoint', 'status'])
api_request_duration = Gauge('nutanix_exporter_api_request_duration_seconds', 'API request duration', ['endpoint'])
scrape_errors = Counter('nutanix_exporter_scrape_errors_total', 'Total scrape errors', ['endpoint'])


class NutanixCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(NUTANIX_USERNAME, NUTANIX_PASSWORD)
        self.session.verify = False
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def _make_request_v3(self, endpoint, body=None):
        """Make v3 API POST request with error handling and metrics."""
        url = f"{BASE_URL}/v3/{endpoint}"
        start_time = time.time()

        try:
            response = self.session.post(url, json=body or {}, timeout=30)
            duration = time.time() - start_time
            api_request_duration.labels(endpoint=endpoint).set(duration)

            if response.status_code == 200:
                api_requests_total.labels(endpoint=endpoint, status='success').inc()
                return response.json()
            else:
                api_requests_total.labels(endpoint=endpoint, status='error').inc()
                logger.error(f"API error {response.status_code} for {endpoint}: {response.text[:200]}")
                return None

        except requests.exceptions.RequestException as e:
            api_requests_total.labels(endpoint=endpoint, status='error').inc()
            scrape_errors.labels(endpoint=endpoint).inc()
            logger.error(f"Request failed for {endpoint}: {e}")
            return None

    def _make_request_v4(self, endpoint):
        """Make v4 API GET request with error handling."""
        url = f"https://{NUTANIX_HOST}:9440/api/{endpoint}"
        start_time = time.time()

        try:
            response = self.session.get(url, timeout=30)
            duration = time.time() - start_time
            api_request_duration.labels(endpoint=endpoint).set(duration)

            if response.status_code == 200:
                api_requests_total.labels(endpoint=endpoint, status='success').inc()
                return response.json()
            else:
                api_requests_total.labels(endpoint=endpoint, status='error').inc()
                if response.status_code != 404:  # Don't log 404s for optional endpoints
                    logger.error(f"API error {response.status_code} for {endpoint}: {response.text[:200]}")
                return None

        except requests.exceptions.RequestException as e:
            api_requests_total.labels(endpoint=endpoint, status='error').inc()
            scrape_errors.labels(endpoint=endpoint).inc()
            logger.error(f"Request failed for {endpoint}: {e}")
            return None

    def _make_request_v2(self, endpoint):
        """Make v2 API GET request with error handling."""
        url = f"{BASE_URL}/v2.0/{endpoint}"
        start_time = time.time()

        try:
            response = self.session.get(url, timeout=30)
            duration = time.time() - start_time
            api_request_duration.labels(endpoint=endpoint).set(duration)

            if response.status_code == 200:
                api_requests_total.labels(endpoint=endpoint, status='success').inc()
                return response.json()
            else:
                api_requests_total.labels(endpoint=endpoint, status='error').inc()
                logger.error(f"API error {response.status_code} for {endpoint}: {response.text[:200]}")
                return None

        except requests.exceptions.RequestException as e:
            api_requests_total.labels(endpoint=endpoint, status='error').inc()
            scrape_errors.labels(endpoint=endpoint).inc()
            logger.error(f"Request failed for {endpoint}: {e}")
            return None

    def collect_clusters(self):
        """Collect cluster metrics using v2 and v3 APIs."""
        logger.info("Collecting cluster metrics...")

        # Use v2 API for detailed stats (CPU, memory, storage)
        v2_data = self._make_request_v2("clusters")

        # Use v3 API for cluster list and UUID mapping
        v3_data = self._make_request_v3("clusters/list", {"kind": "cluster", "length": 100})

        cluster_map = {}

        # Build UUID map from v3
        if v3_data:
            for cluster in v3_data.get('entities', []):
                metadata = cluster.get('metadata', {})
                spec = cluster.get('spec', {})
                status = cluster.get('status', {})
                cluster_uuid = metadata.get('uuid', '')
                cluster_name = spec.get('name', status.get('name', 'unknown'))
                cluster_map[cluster_uuid] = cluster_name

        # Process v2 clusters for stats
        if v2_data:
            for cluster in v2_data.get('entities', []):
                cluster_uuid = cluster.get('uuid', cluster.get('cluster_uuid', 'unknown'))
                cluster_name = cluster.get('name', 'unknown')

                # Update cluster_map if not already set
                if cluster_uuid not in cluster_map:
                    cluster_map[cluster_uuid] = cluster_name

                # Set cluster info
                cluster_info.info({
                    'cluster_name': cluster_name,
                    'cluster_uuid': cluster_uuid
                })

                # Node count
                num_nodes = cluster.get('num_nodes', 0)
                cluster_node_count.labels(cluster_name=cluster_name, cluster_uuid=cluster_uuid).set(num_nodes)

                # Get stats (ppm = parts per million, divide by 10000 for percent)
                stats = cluster.get('stats', {})

                # CPU usage
                cpu_ppm = int(stats.get('hypervisor_cpu_usage_ppm', 0))
                cpu_percent = cpu_ppm / 10000
                cluster_cpu_usage.labels(cluster_name=cluster_name, cluster_uuid=cluster_uuid).set(cpu_percent)

                # Memory usage
                memory_ppm = int(stats.get('hypervisor_memory_usage_ppm', 0))
                memory_percent = memory_ppm / 10000
                cluster_memory_usage.labels(cluster_name=cluster_name, cluster_uuid=cluster_uuid).set(memory_percent)

                # Storage stats from usage_stats
                usage_stats = cluster.get('usage_stats', {})
                storage_usage = int(usage_stats.get('storage.usage_bytes', 0))
                storage_capacity = int(usage_stats.get('storage.capacity_bytes', 0))
                storage_free = int(usage_stats.get('storage.free_bytes', 0))

                cluster_storage_usage.labels(cluster_name=cluster_name, cluster_uuid=cluster_uuid).set(storage_usage)
                cluster_storage_capacity.labels(cluster_name=cluster_name, cluster_uuid=cluster_uuid).set(storage_capacity)
                cluster_storage_free.labels(cluster_name=cluster_name, cluster_uuid=cluster_uuid).set(storage_free)

                # Physical CPU cores (from cluster or sum of hosts)
                total_cores = cluster.get('num_cpu_cores', 0)
                if not total_cores:
                    # Try to get from cluster stats
                    total_cores = cluster.get('total_cpu_cores', 0)
                cluster_physical_cpu_cores.labels(cluster_name=cluster_name, cluster_uuid=cluster_uuid).set(total_cores)

                logger.info(f"Collected metrics for cluster: {cluster_name} (CPU: {cpu_percent:.1f}%, Mem: {memory_percent:.1f}%, Cores: {total_cores})")

        return cluster_map

    def collect_vms(self, cluster_map):
        """Collect VM metrics using v3 API."""
        logger.info("Collecting VM metrics...")

        all_vms = []
        offset = 0
        length = 500

        while True:
            data = self._make_request_v3("vms/list", {"kind": "vm", "length": length, "offset": offset})
            if not data:
                break

            vms = data.get('entities', [])
            if not vms:
                break

            all_vms.extend(vms)
            total = data.get('metadata', {}).get('total_matches', 0)

            if len(all_vms) >= total:
                break
            offset += length

        # Count VMs per cluster
        vm_counts = {}

        for vm in all_vms:
            metadata = vm.get('metadata', {})
            spec = vm.get('spec', {})
            status = vm.get('status', {})

            vm_uuid = metadata.get('uuid', 'unknown')
            vm_name = spec.get('name', status.get('name', 'unknown'))

            # Get cluster reference
            cluster_ref = spec.get('cluster_reference', {})
            cluster_uuid = cluster_ref.get('uuid', '')
            cluster_name = cluster_map.get(cluster_uuid, cluster_ref.get('name', 'unknown'))

            # Count VMs per cluster
            vm_counts[cluster_name] = vm_counts.get(cluster_name, 0) + 1

            # Power state
            resources = status.get('resources', {})
            power_state = resources.get('power_state', 'UNKNOWN')
            power_state_value = 1 if power_state == 'ON' else 0
            vm_power_state.labels(vm_name=vm_name, vm_uuid=vm_uuid, cluster_name=cluster_name).set(power_state_value)

            # CPU count
            spec_resources = spec.get('resources', {})
            num_sockets = spec_resources.get('num_sockets', 1)
            num_vcpus_per_socket = spec_resources.get('num_vcpus_per_socket', 1)
            total_vcpus = num_sockets * num_vcpus_per_socket
            vm_cpu_count.labels(vm_name=vm_name, vm_uuid=vm_uuid).set(total_vcpus)

            # Memory (in bytes, spec gives MiB)
            memory_mib = spec_resources.get('memory_size_mib', 0)
            vm_memory_bytes.labels(vm_name=vm_name, vm_uuid=vm_uuid).set(memory_mib * 1024 * 1024)

            # Disk size (sum of all disks)
            disk_list = spec_resources.get('disk_list', [])
            total_disk_size = 0
            for disk in disk_list:
                disk_size = disk.get('disk_size_bytes', 0)
                if disk_size:
                    total_disk_size += disk_size
                else:
                    # Try disk_size_mib
                    disk_size_mib = disk.get('disk_size_mib', 0)
                    total_disk_size += disk_size_mib * 1024 * 1024
            vm_disk_size_bytes.labels(vm_name=vm_name, vm_uuid=vm_uuid).set(total_disk_size)

        # Set VM counts per cluster
        for cluster_name, count in vm_counts.items():
            vm_count.labels(cluster_name=cluster_name).set(count)

        logger.info(f"Collected metrics for {len(all_vms)} VMs")

    def collect_hosts(self, cluster_map):
        """Collect host metrics using v3 API."""
        logger.info("Collecting host metrics...")

        data = self._make_request_v3("hosts/list", {"kind": "host", "length": 500})
        if not data:
            return

        hosts = data.get('entities', [])
        host_counts = {}

        for host in hosts:
            metadata = host.get('metadata', {})
            spec = host.get('spec', {})
            status = host.get('status', {})

            host_uuid = metadata.get('uuid', 'unknown')
            host_name = spec.get('name', status.get('name', 'unknown'))

            # Get cluster reference
            cluster_ref = status.get('cluster_reference', {})
            cluster_uuid = cluster_ref.get('uuid', '')
            cluster_name = cluster_map.get(cluster_uuid, cluster_ref.get('name', 'unknown'))

            # Count hosts per cluster
            host_counts[cluster_name] = host_counts.get(cluster_name, 0) + 1

            # Get host stats from resources
            resources = status.get('resources', {})

            # CPU usage
            cpu_usage = resources.get('hypervisor', {}).get('cpu_usage_ppm', 0) / 10000  # ppm to percent
            host_cpu_usage.labels(host_name=host_name, host_uuid=host_uuid, cluster_name=cluster_name).set(cpu_usage)

            # Memory usage
            memory_usage = resources.get('hypervisor', {}).get('memory_usage_ppm', 0) / 10000
            host_memory_usage.labels(host_name=host_name, host_uuid=host_uuid, cluster_name=cluster_name).set(memory_usage)

            # Number of VMs
            num_vms = resources.get('hypervisor', {}).get('num_vms', 0)
            host_num_vms.labels(host_name=host_name, host_uuid=host_uuid, cluster_name=cluster_name).set(num_vms)

            # Physical CPU cores and sockets
            cpu_capacity = resources.get('cpu_capacity_hz', 0)
            num_cpu_cores = resources.get('num_cpu_cores', 0)
            num_cpu_sockets = resources.get('num_cpu_sockets', 0)

            host_physical_cpu_cores.labels(host_name=host_name, host_uuid=host_uuid, cluster_name=cluster_name).set(num_cpu_cores)
            host_cpu_sockets.labels(host_name=host_name, host_uuid=host_uuid, cluster_name=cluster_name).set(num_cpu_sockets)

        # Set host counts per cluster
        for cluster_name, count in host_counts.items():
            host_count.labels(cluster_name=cluster_name).set(count)

        logger.info(f"Collected metrics for {len(hosts)} hosts")

    def collect_storage_containers(self):
        """Collect storage container metrics using v2 API."""
        logger.info("Collecting storage container metrics...")

        data = self._make_request_v2("storage_containers")
        if not data:
            return

        containers = data.get('entities', [])

        for container in containers:
            container_uuid = container.get('storage_container_uuid', 'unknown')
            container_name = container.get('name', 'unknown')

            # Usage stats
            usage_stats = container.get('usage_stats', {})

            # Storage usage
            usage = usage_stats.get('storage.user_unreserved_usage_bytes', 0)
            storage_container_usage.labels(container_name=container_name, container_uuid=container_uuid).set(int(usage))

            # Storage capacity
            capacity = usage_stats.get('storage.user_capacity_bytes', 0)
            storage_container_capacity.labels(container_name=container_name, container_uuid=container_uuid).set(int(capacity))

        logger.info(f"Collected metrics for {len(containers)} storage containers")

    def collect_file_servers(self):
        """Collect file server metrics using Files v4 API."""
        logger.info("Collecting file server metrics...")

        # Get file servers list
        data = self._make_request_v4("files/v4.0/config/file-servers")
        if not data:
            logger.info("No file servers found or Files API not available")
            return

        file_servers = data.get('data', [])
        if not file_servers:
            logger.info("No file servers configured")
            return

        for fs in file_servers:
            fs_uuid = fs.get('extId', 'unknown')
            fs_name = fs.get('name', 'unknown')

            # Get file server stats
            stats_data = self._make_request_v4(f"files/v4.0/stats/file-servers/{fs_uuid}")
            if stats_data:
                stats = stats_data.get('data', {})

                # Storage capacity metrics
                capacity = stats.get('storageCapacityBytes', 0)
                used = stats.get('usedCapacityBytes', 0)
                available = stats.get('availableCapacityBytes', 0)

                if capacity:
                    file_server_capacity.labels(file_server_name=fs_name, file_server_uuid=fs_uuid).set(capacity)
                if used:
                    file_server_used.labels(file_server_name=fs_name, file_server_uuid=fs_uuid).set(used)
                if available:
                    file_server_available.labels(file_server_name=fs_name, file_server_uuid=fs_uuid).set(available)

                # Other metrics from time series (take latest value)
                num_files = stats.get('numberOfFiles', [])
                if num_files and isinstance(num_files, list) and len(num_files) > 0:
                    file_server_files_count.labels(file_server_name=fs_name, file_server_uuid=fs_uuid).set(num_files[-1].get('value', 0))

                num_connections = stats.get('numberOfConnections', [])
                if num_connections and isinstance(num_connections, list) and len(num_connections) > 0:
                    file_server_connections.labels(file_server_name=fs_name, file_server_uuid=fs_uuid).set(num_connections[-1].get('value', 0))

                logger.info(f"Collected metrics for file server: {fs_name} (used: {used/(1024**4):.2f} TiB)")
            else:
                logger.warning(f"Could not get stats for file server: {fs_name}")

        logger.info(f"Collected metrics for {len(file_servers)} file servers")

    def collect_all(self):
        """Collect all metrics."""
        try:
            cluster_map = self.collect_clusters()
            self.collect_vms(cluster_map)
            self.collect_hosts(cluster_map)
            self.collect_storage_containers()
            self.collect_file_servers()
            logger.info("Metrics collection completed successfully")
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")


def main():
    """Main entry point."""
    logger.info(f"Starting Nutanix Exporter on port {EXPORTER_PORT}")
    logger.info(f"Connecting to Nutanix Prism Central: {NUTANIX_HOST}")

    # Start Prometheus HTTP server
    start_http_server(EXPORTER_PORT)
    logger.info(f"Prometheus metrics available at http://localhost:{EXPORTER_PORT}/metrics")

    # Create collector
    collector = NutanixCollector()

    # Initial collection
    collector.collect_all()

    # Continuous collection loop
    while True:
        time.sleep(SCRAPE_INTERVAL)
        collector.collect_all()


if __name__ == '__main__':
    main()
