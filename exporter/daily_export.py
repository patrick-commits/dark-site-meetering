#!/usr/bin/env python3
"""
Nutanix Daily CSV Export

Exports VM resource data in billing/metering format:
accountId, qty, startDate, endDate, meteredItem, appid, sno, fqdn, type, description, guid
"""

import os
import csv
import logging
from datetime import datetime, timedelta
import requests
from requests.auth import HTTPBasicAuth
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
ACCOUNT_ID = os.getenv('ACCOUNT_ID', 'default')
APP_ID = os.getenv('APP_ID', '')
EXPORT_DIR = os.getenv('EXPORT_DIR', '/data/exports')

# Base URL for Nutanix API
BASE_URL = f"https://{NUTANIX_HOST}:9440/api/nutanix"


class NutanixExporter:
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(NUTANIX_USERNAME, NUTANIX_PASSWORD)
        self.session.verify = False
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self.cluster_map = {}

    def _make_request_v3(self, endpoint, body=None):
        """Make v3 API POST request with error handling."""
        url = f"{BASE_URL}/v3/{endpoint}"
        try:
            response = self.session.post(url, json=body or {}, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API error {response.status_code} for {endpoint}: {response.text[:200]}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {e}")
            return None

    def _make_request_v4(self, endpoint):
        """Make v4 API GET request with error handling."""
        url = f"https://{NUTANIX_HOST}:9440/api/{endpoint}"
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                if response.status_code != 404:
                    logger.error(f"API error {response.status_code} for {endpoint}: {response.text[:200]}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {e}")
            return None

    def get_clusters(self):
        """Fetch clusters and build UUID to name mapping."""
        data = self._make_request_v3("clusters/list", {"kind": "cluster", "length": 100})
        if not data:
            return {}

        for cluster in data.get('entities', []):
            metadata = cluster.get('metadata', {})
            spec = cluster.get('spec', {})
            status = cluster.get('status', {})
            uuid = metadata.get('uuid', '')
            name = spec.get('name', status.get('name', 'unknown'))
            self.cluster_map[uuid] = name

        return self.cluster_map

    def get_vms(self):
        """Fetch all VMs from Prism Central using v3 API."""
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
            logger.info(f"Fetched {len(all_vms)}/{total} VMs")

            if len(all_vms) >= total:
                break
            offset += length

        return all_vms

    def get_file_servers(self):
        """Fetch file servers and their storage stats using v4 API."""
        file_servers = []

        # Get file servers list
        data = self._make_request_v4("files/v4.0/config/file-servers")
        if not data:
            logger.info("No file servers found or Files API not available")
            return file_servers

        for fs in data.get('data', []):
            fs_uuid = fs.get('extId', '')
            fs_name = fs.get('name', 'unknown')

            # Get file server stats
            stats_data = self._make_request_v4(f"files/v4.0/stats/file-servers/{fs_uuid}")
            if stats_data:
                stats = stats_data.get('data', {})
                file_servers.append({
                    'uuid': fs_uuid,
                    'name': fs_name,
                    'capacity_bytes': stats.get('storageCapacityBytes', 0),
                    'used_bytes': stats.get('usedCapacityBytes', 0),
                    'available_bytes': stats.get('availableCapacityBytes', 0),
                })

        logger.info(f"Fetched {len(file_servers)} file servers")
        return file_servers

    def export_to_csv(self, output_path=None):
        """Export VM data to CSV in billing format."""
        # Calculate date range (yesterday for daily export)
        end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=1)

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        # Generate output filename
        if not output_path:
            os.makedirs(EXPORT_DIR, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = os.path.join(EXPORT_DIR, f'nutanix_export_{timestamp}.csv')

        logger.info(f"Starting export for period {start_date_str} to {end_date_str}")

        # Fetch clusters first for name mapping
        self.get_clusters()

        # Fetch VMs
        vms = self.get_vms()
        if not vms:
            logger.warning("No VMs found to export")
            return None

        # Prepare CSV data
        rows = []
        sno = 1

        for vm in vms:
            metadata = vm.get('metadata', {})
            spec = vm.get('spec', {})
            status = vm.get('status', {})

            vm_uuid = metadata.get('uuid', '')
            vm_name = spec.get('name', status.get('name', 'unknown'))
            vm_description = spec.get('description', '')

            # Get cluster name
            cluster_ref = spec.get('cluster_reference', {})
            cluster_uuid = cluster_ref.get('uuid', '')
            cluster_name = self.cluster_map.get(cluster_uuid, ACCOUNT_ID)

            # Calculate resources from spec
            spec_resources = spec.get('resources', {})
            num_sockets = spec_resources.get('num_sockets', 1)
            num_vcpus_per_socket = spec_resources.get('num_vcpus_per_socket', 1)
            total_vcpus = num_sockets * num_vcpus_per_socket

            memory_mib = spec_resources.get('memory_size_mib', 0)
            memory_gb = round(memory_mib / 1024, 2)

            # Calculate total disk size
            disk_list = spec_resources.get('disk_list', [])
            total_disk_bytes = 0
            for disk in disk_list:
                disk_size = disk.get('disk_size_bytes', 0)
                if disk_size:
                    total_disk_bytes += disk_size
                else:
                    disk_size_mib = disk.get('disk_size_mib', 0)
                    total_disk_bytes += disk_size_mib * 1024 * 1024
            total_disk_gb = round(total_disk_bytes / (1024 ** 3), 2)

            # Create row for vCPU
            rows.append({
                'accountId': cluster_name,
                'qty': total_vcpus,
                'startDate': start_date_str,
                'endDate': end_date_str,
                'meteredItem': 'vCPU',
                'appid': APP_ID,
                'sno': sno,
                'fqdn': vm_name,
                'type': 'VM',
                'description': f'vCPU allocation for {vm_name}',
                'guid': vm_uuid
            })
            sno += 1

            # Create row for Memory
            rows.append({
                'accountId': cluster_name,
                'qty': memory_gb,
                'startDate': start_date_str,
                'endDate': end_date_str,
                'meteredItem': 'Memory_GB',
                'appid': APP_ID,
                'sno': sno,
                'fqdn': vm_name,
                'type': 'VM',
                'description': f'Memory allocation for {vm_name}',
                'guid': vm_uuid
            })
            sno += 1

            # Create row for Storage
            rows.append({
                'accountId': cluster_name,
                'qty': total_disk_gb,
                'startDate': start_date_str,
                'endDate': end_date_str,
                'meteredItem': 'Storage_GB',
                'appid': APP_ID,
                'sno': sno,
                'fqdn': vm_name,
                'type': 'VM',
                'description': f'Storage allocation for {vm_name}',
                'guid': vm_uuid
            })
            sno += 1

        # Fetch and add file servers
        file_servers = self.get_file_servers()
        for fs in file_servers:
            fs_name = fs.get('name', 'unknown')
            fs_uuid = fs.get('uuid', '')
            used_bytes = fs.get('used_bytes', 0)
            used_tib = round(used_bytes / (1024 ** 4), 4)  # Convert to TiB

            if used_bytes > 0:  # Only include if there's usage
                rows.append({
                    'accountId': ACCOUNT_ID,
                    'qty': used_tib,
                    'startDate': start_date_str,
                    'endDate': end_date_str,
                    'meteredItem': 'Files_TiB',
                    'appid': APP_ID,
                    'sno': sno,
                    'fqdn': fs_name,
                    'type': 'FileServer',
                    'description': f'Files consumed storage for {fs_name}',
                    'guid': fs_uuid
                })
                sno += 1

        # Write CSV (tab-separated)
        fieldnames = ['accountId', 'qty', 'startDate', 'endDate', 'meteredItem',
                      'appid', 'sno', 'fqdn', 'type', 'description', 'guid']

        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter='\t')
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Exported {len(rows)} records ({len(vms)} VMs, {len(file_servers)} file servers) to {output_path}")
        return output_path


def main():
    """Main entry point for daily export."""
    logger.info(f"Starting daily export from Nutanix Prism Central: {NUTANIX_HOST}")

    exporter = NutanixExporter()
    output_file = exporter.export_to_csv()

    if output_file:
        logger.info(f"Export completed successfully: {output_file}")
    else:
        logger.error("Export failed")
        exit(1)


if __name__ == '__main__':
    main()
