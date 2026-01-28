#!/usr/bin/env python3
"""
Dark Site Metering - Daily CSV Export

Exports metering data in billing format:
accountId, qty, startDate, endDate, meteredItem, appid, sno, fqdn, type, description, guid

Metered items:
- Cores: Physical CPU cores from hosts
- Files_TiB: File server storage consumed in TiB
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
ACCOUNT_ID = os.getenv('ACCOUNT_ID', '123456')  # Default account ID for metering
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

    def get_hosts_with_cores(self):
        """Fetch hosts and their physical CPU cores."""
        hosts = []

        data = self._make_request_v3("hosts/list", {"kind": "host", "length": 500})
        if not data:
            logger.warning("No hosts found")
            return hosts

        for host in data.get('entities', []):
            metadata = host.get('metadata', {})
            spec = host.get('spec', {})
            status = host.get('status', {})
            resources = status.get('resources', {})

            host_uuid = metadata.get('uuid', '')
            host_name = spec.get('name', status.get('name', 'unknown'))

            # Get cluster reference
            cluster_ref = status.get('cluster_reference', {})
            cluster_uuid = cluster_ref.get('uuid', '')
            cluster_name = self.cluster_map.get(cluster_uuid, cluster_ref.get('name', 'unknown'))

            # Get physical CPU cores
            num_cpu_cores = resources.get('num_cpu_cores', 0)
            num_cpu_sockets = resources.get('num_cpu_sockets', 0)

            hosts.append({
                'uuid': host_uuid,
                'name': host_name,
                'cluster_name': cluster_name,
                'num_cpu_cores': num_cpu_cores,
                'num_cpu_sockets': num_cpu_sockets,
            })

        logger.info(f"Fetched {len(hosts)} hosts")
        return hosts

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
                used_bytes = stats.get('usedCapacityBytes', 0)
                capacity_bytes = stats.get('storageCapacityBytes', 0)

                file_servers.append({
                    'uuid': fs_uuid,
                    'name': fs_name,
                    'capacity_bytes': capacity_bytes,
                    'used_bytes': used_bytes,
                })

        logger.info(f"Fetched {len(file_servers)} file servers")
        return file_servers

    def export_to_csv(self, output_path=None):
        """Export metering data to CSV in billing format."""
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

        # Prepare CSV data
        rows = []
        sno = 1

        # Get hosts with physical CPU cores
        hosts = self.get_hosts_with_cores()
        total_cores = 0

        for host in hosts:
            host_name = host.get('name', 'unknown')
            host_uuid = host.get('uuid', '')
            num_cores = host.get('num_cpu_cores', 0)
            total_cores += num_cores

            if num_cores > 0:
                rows.append({
                    'accountId': ACCOUNT_ID,
                    'qty': num_cores,
                    'startDate': start_date_str,
                    'endDate': end_date_str,
                    'meteredItem': 'Cores',
                    'appid': APP_ID,
                    'sno': sno,
                    'fqdn': host_name,
                    'type': 'Host',
                    'description': f'Physical CPU cores for host {host_name}',
                    'guid': host_uuid
                })
                sno += 1

        # Get file servers with storage usage
        file_servers = self.get_file_servers()

        for fs in file_servers:
            fs_name = fs.get('name', 'unknown')
            fs_uuid = fs.get('uuid', '')
            used_bytes = fs.get('used_bytes', 0)

            # Convert bytes to TiB (1 TiB = 1024^4 bytes)
            used_tib = round(used_bytes / (1024 ** 4), 4)

            # Always include file server entry (even if 0)
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

        logger.info(f"Exported {len(rows)} records (Total cores: {total_cores}, File servers: {len(file_servers)}) to {output_path}")
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
