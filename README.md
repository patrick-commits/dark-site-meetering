# Dark Site Metering

A complete metering solution for Nutanix Prism Central in dark site environments. Collects usage metrics via the Nutanix API, stores them in Prometheus, visualizes them in Grafana, and exports daily billing/metering reports for offline consumption tracking.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Components](#components)
- [Metrics Collected](#metrics-collected)
- [Daily Export](#daily-export)
- [Grafana Dashboards](#grafana-dashboards)
- [API Reference](#api-reference)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Nutanix Prism Central                       │
│                      (API v2, v3, v4)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                    HTTPS API calls
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Docker Containers                          │
├────────────────────────────┬────────────────────────────────────┤
│  nutanix-exporter          │  nutanix-daily-export              │
│  - Polls API every 60s     │  - Scheduled CSV export            │
│  - Prometheus metrics      │  - Runs daily at 01:00             │
│  - Port 9090               │  - Billing/metering format         │
└────────────────────────────┴────────────────────────────────────┘
          │                                      │
          ▼                                      ▼
┌─────────────────────┐              ┌─────────────────────────────┐
│  Prometheus         │              │  Local Filesystem           │
│  - Time-series DB   │              │  ./exports/*.csv            │
│  - 15 day retention │              │                             │
│  - Port 9091        │              │                             │
└─────────────────────┘              └─────────────────────────────┘
          │
          ▼
┌─────────────────────┐
│  Grafana            │
│  - Dashboards       │
│  - Port 3000        │
└─────────────────────┘
```

---

## Prerequisites

- **Docker Desktop** (with Docker Compose)
- **Network access** to Nutanix Prism Central on port 9440
- **Prism Central credentials** (admin user or service account)

---

## Quick Start

### 1. Configure Credentials

Edit the `.env` file with your Prism Central details:

```bash
# Nutanix Prism Central Configuration
NUTANIX_HOST=10.38.66.7
NUTANIX_USERNAME=admin
NUTANIX_PASSWORD=your-password

# Daily Export Configuration
ACCOUNT_ID=default
APP_ID=
EXPORT_TIME=01:00
```

### 2. Start the Stack

```bash
cd ~/nutanix-monitoring
docker compose up -d
```

### 3. Access the Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9091 | - |
| Exporter Metrics | http://localhost:9090/metrics | - |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NUTANIX_HOST` | - | Prism Central IP or hostname |
| `NUTANIX_USERNAME` | admin | API username |
| `NUTANIX_PASSWORD` | - | API password |
| `SCRAPE_INTERVAL` | 60 | How often to poll the API (seconds) |
| `EXPORT_TIME` | 01:00 | When to run daily export (24h format) |
| `ACCOUNT_ID` | default | Account ID for billing export |
| `APP_ID` | - | Application ID for billing export |

### Files

| File | Purpose |
|------|---------|
| `.env` | Environment configuration |
| `docker-compose.yml` | Container orchestration |
| `prometheus/prometheus.yml` | Prometheus scrape config |
| `grafana/provisioning/` | Grafana datasources and dashboards |
| `exporter/` | Python exporter source code |

---

## Components

### 1. Nutanix Exporter (`nutanix-exporter`)

A Python application that:
- Connects to Prism Central API
- Collects metrics every 60 seconds
- Exposes metrics in Prometheus format at `/metrics`

**APIs Used:**
- v2 API: Clusters (stats), Storage Containers
- v3 API: VMs, Hosts, Clusters (list)
- v4 API: File Servers

### 2. Daily Export Scheduler (`nutanix-daily-export`)

A Python scheduler that:
- Runs daily at configured time (default: 01:00)
- Exports VM and File Server data to CSV
- Saves files to `./exports/` directory

### 3. Prometheus

Time-series database that:
- Scrapes metrics from the exporter every 60 seconds
- Stores data for 15 days (default)
- Provides query interface for Grafana

### 4. Grafana

Visualization platform with:
- Pre-configured Prometheus datasource
- Nutanix Overview dashboard
- Real-time metrics display

---

## Metrics Collected

### Cluster Metrics

| Metric | Description | Labels |
|--------|-------------|--------|
| `nutanix_cluster_cpu_usage_percent` | Cluster CPU usage % | cluster_name, cluster_uuid |
| `nutanix_cluster_memory_usage_percent` | Cluster memory usage % | cluster_name, cluster_uuid |
| `nutanix_cluster_storage_usage_bytes` | Storage used (bytes) | cluster_name, cluster_uuid |
| `nutanix_cluster_storage_capacity_bytes` | Storage capacity (bytes) | cluster_name, cluster_uuid |
| `nutanix_cluster_storage_free_bytes` | Storage free (bytes) | cluster_name, cluster_uuid |
| `nutanix_cluster_node_count` | Number of nodes | cluster_name, cluster_uuid |

### VM Metrics

| Metric | Description | Labels |
|--------|-------------|--------|
| `nutanix_vm_count` | Total VMs per cluster | cluster_name |
| `nutanix_vm_power_state` | Power state (1=ON, 0=OFF) | vm_name, vm_uuid, cluster_name |
| `nutanix_vm_cpu_count` | vCPU count | vm_name, vm_uuid |
| `nutanix_vm_memory_bytes` | Memory allocated (bytes) | vm_name, vm_uuid |
| `nutanix_vm_disk_size_bytes` | Total disk size (bytes) | vm_name, vm_uuid |

### Host Metrics

| Metric | Description | Labels |
|--------|-------------|--------|
| `nutanix_host_count` | Total hosts per cluster | cluster_name |
| `nutanix_host_cpu_usage_percent` | Host CPU usage % | host_name, host_uuid, cluster_name |
| `nutanix_host_memory_usage_percent` | Host memory usage % | host_name, host_uuid, cluster_name |
| `nutanix_host_num_vms` | VMs on host | host_name, host_uuid, cluster_name |

### Storage Container Metrics

| Metric | Description | Labels |
|--------|-------------|--------|
| `nutanix_storage_container_usage_bytes` | Container usage (bytes) | container_name, container_uuid |
| `nutanix_storage_container_capacity_bytes` | Container capacity (bytes) | container_name, container_uuid |

### File Server Metrics

| Metric | Description | Labels |
|--------|-------------|--------|
| `nutanix_file_server_capacity_bytes` | File server capacity (bytes) | file_server_name, file_server_uuid |
| `nutanix_file_server_used_bytes` | File server used (bytes) | file_server_name, file_server_uuid |
| `nutanix_file_server_available_bytes` | File server available (bytes) | file_server_name, file_server_uuid |
| `nutanix_file_server_files_count` | Number of files | file_server_name, file_server_uuid |
| `nutanix_file_server_connections` | Active connections | file_server_name, file_server_uuid |

---

## Daily Export

### Export Format

The daily export produces a tab-separated CSV file with billing/metering data:

| Column | Description |
|--------|-------------|
| accountId | Cluster name or configured ACCOUNT_ID |
| qty | Quantity (vCPUs, GB, TiB) |
| startDate | Period start (YYYY-MM-DD) |
| endDate | Period end (YYYY-MM-DD) |
| meteredItem | Type: vCPU, Memory_GB, Storage_GB, Files_TiB |
| appid | Application ID (from config) |
| sno | Serial number (row index) |
| fqdn | VM or File Server name |
| type | VM or FileServer |
| description | Human-readable description |
| guid | UUID of the resource |

### Sample Output

```
accountId    qty    startDate    endDate      meteredItem  appid  sno  fqdn      type  description                    guid
PHX-POC294   4      2026-01-25   2026-01-26   vCPU               1    web-vm    VM    vCPU allocation for web-vm    abc-123...
PHX-POC294   8.0    2026-01-25   2026-01-26   Memory_GB          2    web-vm    VM    Memory allocation for web-vm  abc-123...
PHX-POC294   100.0  2026-01-25   2026-01-26   Storage_GB         3    web-vm    VM    Storage allocation for web-vm abc-123...
default      5.5    2026-01-25   2026-01-26   Files_TiB          4    labFS     FS    Files consumed for labFS      def-456...
```

### Export Location

Files are saved to: `~/nutanix-monitoring/exports/`

Filename format: `nutanix_export_YYYYMMDD_HHMMSS.csv`

### Manual Export

Run an export manually:

```bash
docker exec nutanix-daily-export python daily_export.py
```

### Schedule Configuration

Change export time in `.env`:

```bash
EXPORT_TIME=06:00  # Run at 6:00 AM
```

Then restart:

```bash
docker compose restart nutanix-daily-export
```

---

## Grafana Dashboards

### Dark Site Overview Dashboard

Access: http://localhost:3000/d/nutanix-overview/

**Panels:**
- Cluster CPU Usage (gauge)
- Cluster Memory Usage (gauge)
- Cluster Storage (pie chart)
- Total VMs / Total Hosts (stat)
- VMs Running / Stopped (stat)
- Host CPU Usage (time series)
- Host Memory Usage (time series)
- Virtual Machines table
- Storage Container Usage (bar gauge)

### Creating Custom Dashboards

1. Go to Grafana → Dashboards → New
2. Add panels using Prometheus queries
3. Example queries:
   - `nutanix_vm_count` - VM count by cluster
   - `sum(nutanix_vm_memory_bytes)` - Total VM memory
   - `rate(nutanix_cluster_cpu_usage_percent[5m])` - CPU trend

---

## API Reference

### Nutanix APIs Used

| API Version | Endpoint | Method | Purpose |
|-------------|----------|--------|---------|
| v2 | `/api/nutanix/v2.0/clusters` | GET | Cluster stats (CPU, memory, storage) |
| v2 | `/api/nutanix/v2.0/storage_containers` | GET | Storage container metrics |
| v3 | `/api/nutanix/v3/clusters/list` | POST | Cluster list and UUIDs |
| v3 | `/api/nutanix/v3/vms/list` | POST | VM details and resources |
| v3 | `/api/nutanix/v3/hosts/list` | POST | Host details and stats |
| v4 | `/api/files/v4.0/config/file-servers` | GET | File server list |
| v4 | `/api/files/v4.0/stats/file-servers/{id}` | GET | File server storage stats |

### Rate Limits

Nutanix API rate limits by Prism Central size:

| Size | Memory | Rate Limit |
|------|--------|------------|
| X-Small | 18 GB | 30 req/sec |
| Small | 26 GB | 40 req/sec |
| Large | 44 GB | 60 req/sec |
| X-Large | 60 GB | 80 req/sec |

The exporter is configured to stay well within these limits.

---

## Maintenance

### View Logs

```bash
# Exporter logs
docker logs -f nutanix-exporter

# Daily export logs
docker logs -f nutanix-daily-export

# All services
docker compose logs -f
```

### Restart Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart nutanix-exporter
```

### Update Configuration

1. Edit `.env` file
2. Recreate containers:
   ```bash
   docker compose up -d --force-recreate
   ```

### Backup Data

```bash
# Backup Prometheus data
docker run --rm -v nutanix-monitoring_prometheus_data:/data -v $(pwd):/backup alpine tar czf /backup/prometheus-backup.tar.gz /data

# Backup export files
cp -r ~/nutanix-monitoring/exports ~/nutanix-exports-backup
```

### Stop Everything

```bash
docker compose down
```

### Remove Everything (including data)

```bash
docker compose down -v
```

---

## Troubleshooting

### Exporter Not Collecting Data

1. Check connectivity:
   ```bash
   nc -zv <PRISM_CENTRAL_IP> 9440
   ```

2. Check credentials:
   ```bash
   curl -k -u admin:password https://<PC_IP>:9440/api/nutanix/v3/clusters/list \
     -H "Content-Type: application/json" -d '{"kind":"cluster"}'
   ```

3. Check exporter logs:
   ```bash
   docker logs nutanix-exporter
   ```

### Grafana Shows No Data

1. Verify Prometheus has data:
   ```bash
   curl -s "http://localhost:9091/api/v1/query?query=nutanix_vm_count"
   ```

2. Check Prometheus targets:
   ```bash
   curl -s http://localhost:9091/api/v1/targets | jq '.data.activeTargets[].health'
   ```

3. Verify datasource in Grafana:
   - Go to Settings → Data Sources → Prometheus
   - Click "Test"

### Export Not Running

1. Check scheduler status:
   ```bash
   docker logs nutanix-daily-export
   ```

2. Run export manually:
   ```bash
   docker exec nutanix-daily-export python daily_export.py
   ```

3. Check export directory permissions:
   ```bash
   ls -la ~/nutanix-monitoring/exports/
   ```

### High API Latency

1. Check API response times in metrics:
   ```bash
   curl -s http://localhost:9090/metrics | grep api_request_duration
   ```

2. Increase scrape interval if needed:
   ```bash
   # In .env
   SCRAPE_INTERVAL=120
   ```

---

## File Structure

```
nutanix-monitoring/
├── .env                          # Configuration
├── .env.example                  # Configuration template
├── docker-compose.yml            # Container orchestration
├── README.md                     # This documentation
├── exports/                      # Daily export CSV files
│   └── nutanix_export_*.csv
├── exporter/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── nutanix_exporter.py       # Prometheus exporter
│   ├── daily_export.py           # CSV export logic
│   └── daily_export_scheduler.py # Export scheduler
├── grafana/
│   └── provisioning/
│       ├── dashboards/
│       │   ├── dashboard.yml
│       │   └── nutanix-overview.json
│       └── datasources/
│           └── datasource.yml
└── prometheus/
    └── prometheus.yml            # Prometheus config
```

---

## License

Internal use only.

## Support

For issues or questions, contact your system administrator.
