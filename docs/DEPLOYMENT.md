# Deployment Guide: Alibaba Cloud ECS

## Overview

This guide covers deploying the HCM Autopilot Agent on Alibaba Cloud ECS. The application is containerized with Docker and uses Alibaba Cloud's DashScope API (Qwen Cloud Model Studio) for LLM inference.

## Prerequisites

- Alibaba Cloud account with ECS access
- SSH client for remote instance access
- Docker and Docker Compose installed locally (for testing)

## Step 1: Provision an ECS Instance

### Instance Configuration

1. Log in to the **Alibaba Cloud Console**
2. Navigate to **ECS** → **Instances**
3. Click **Create Instance** with the following specifications:
   - **Image:** Ubuntu 22.04 LTS
   - **Instance Type:** >=1 vCPU, >=2 GB memory (recommended: 2 vCPU, 4 GB for production)
   - **Public IP:** Enable (or associate an EIP for static IP)
   - **Security Group:** Create or select one (see next section)

### Security Group Configuration

1. In your ECS instance details, navigate to **Security Groups**
2. Edit the security group and add the following inbound rule:
   - **Protocol:** TCP
   - **Port Range:** 8501
   - **Authorization Object:** 0.0.0.0/0 (for public demo) or restrict to your CIDR range for production
   - **Stateful:** Inbound rules are stateful; return traffic is automatically allowed
   - Note: You can also use the `AuthorizeSecurityGroup` API for programmatic port configuration

### Install Docker and Docker Compose

SSH into your instance and run:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

## Step 2: Clone the Repository and Configure Environment

### Clone the Repo

```bash
cd /opt
sudo git clone https://github.com/your-org/hcm-autopilot-agent.git
cd hcm-autopilot-agent
sudo chown -R $USER:$USER .
```

### Create `.env` File

Create a `.env` file in the project root with the following variables:

```bash
# Required: Qwen Cloud (Alibaba Cloud Model Studio)
QWEN_CLOUD_API_KEY=your_dashscope_api_key_here

# Optional: Alibaba Cloud OSS for publishing onboarding packages
ALIBABA_CLOUD_ACCESS_KEY_ID=your_access_key_id
ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_access_key_secret
OSS_BUCKET=your-bucket-name
OSS_ENDPOINT=https://oss-ap-southeast-1.aliyuncs.com
```

**Getting Your API Key:**
- Log in to [Alibaba Cloud Model Studio (DashScope)](https://dashscope.aliyun.com)
- Navigate to **API Keys** and create a new key
- Copy the key to `QWEN_CLOUD_API_KEY`

**Optional OSS Configuration:**
- Requires IAM access keys from Alibaba Cloud Console
- OSS endpoint format: `https://oss-{region}.aliyuncs.com` (all endpoints are *.aliyuncs.com)
- Only needed if using OSS for package publishing

## Step 3: Build and Start the Application

### Deploy with Docker Compose

```bash
docker compose up -d --build
```

This will:
- Build the Docker image from the Dockerfile
- Start the application in detached mode
- Container listens on port 8501

### Verify Container Health

```bash
docker compose ps
docker compose logs -f
```

The container includes a HEALTHCHECK that probes the Streamlit endpoint at `/_stcore/health`.

## Step 4: Access the Application

Open your browser and navigate to:

```
http://<ecs-public-ip>:8501
```

Replace `<ecs-public-ip>` with your ECS instance's public IP address (found in the Alibaba Cloud Console under **Instance Details** → **Network** → **Public IP Address**).

## Proof of Alibaba Cloud Integration

### DashScope (Qwen Cloud Model Studio)

Our backend leverages **Alibaba Cloud Model Studio (DashScope)** for LLM inference:

- **Location:** `src/utils/qwen_client.py`
- **API:** Calls DashScope endpoints to run inference with Qwen models
- **Environment Variable:** `QWEN_CLOUD_API_KEY` authenticates requests
- **Endpoint:** https://dashscope.aliyuncs.com (all *.aliyuncs.com)

### Alibaba Cloud Object Storage Service (OSS)

Optionally, the application can publish onboarding packages to **Alibaba Cloud OSS**:

- **Location:** `src/utils/oss_client.py`
- **SDK:** Uses `oss2` Python SDK for object storage operations
- **Environment Variables:**
  - `ALIBABA_CLOUD_ACCESS_KEY_ID` — IAM access key
  - `ALIBABA_CLOUD_ACCESS_KEY_SECRET` — IAM access secret
  - `OSS_BUCKET` — target bucket name
  - `OSS_ENDPOINT` — OSS endpoint (e.g., https://oss-ap-southeast-1.aliyuncs.com)
- **Endpoint Format:** All Alibaba Cloud endpoints follow the pattern `https://{service}-{region}.aliyuncs.com`

## Troubleshooting

### Container Won't Start

```bash
docker compose logs
```

Check for missing environment variables or network issues.

### Port 8501 Not Accessible

- Verify the security group rule is in place and applied
- Check that Docker is running: `docker ps`
- Verify the container is healthy: `docker compose ps`

### High Latency on Inference

- Ensure your ECS instance has sufficient vCPU/memory
- Check network latency to Alibaba Cloud Model Studio API
- Consider upgrading to a larger instance type

## Production Considerations

- Use an EIP (Elastic IP) for stable public addressing
- Configure a VPC with restricted CIDR ranges for security
- Use CloudMonitor for ECS instance and application monitoring
- Set up auto-scaling groups for multiple instances
- Use a load balancer (Server Load Balancer / SLB) for traffic distribution
- Store sensitive data (API keys) in Alibaba Cloud Key Management Service (KMS)
- Enable VPC flow logs for network traffic monitoring

## Stopping and Cleanup

```bash
# Stop the application
docker compose down

# Remove all containers and images
docker compose down -v --rmi all

# Delete the ECS instance via the Alibaba Cloud Console if no longer needed
```
