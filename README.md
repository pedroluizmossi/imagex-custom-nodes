# Imagex Nodes for ComfyUI

This repository contains a suite of custom nodes for ComfyUI that integrate directly with the **Imagex** backend services. These nodes enable a resilient, scalable, and asynchronous workflow for generating images and reporting their status.

## Features

-   **SQS Worker Integration**: A resilient background worker that automatically polls an SQS queue for new jobs and submits them to ComfyUI.
-   **Secure S3 Uploader**: Uploads generated assets to a pre-determined S3 path, using secure IAM roles or environment variables for authentication.
-   **Job Completion Notifier**: Sends a structured message to an SQS queue upon successful job completion, enabling backend processing.
-   **Production-Ready**: Built with resilience in mind, including retries with exponential backoff and robust error handling.
-   **Zero-Config (Post-Setup)**: Once environment variables are set, the system runs automatically on ComfyUI startup.

## Installation

1.  **Clone the Repository**:
    Navigate to your ComfyUI `custom_nodes` directory and clone this repository.
    ```bash
    git clone https://github.com/pedroluizmossi/imagex-custom-nodes.git
    ```

2.  **Install Dependencies**:
    Install the required Python packages using the provided `requirements.txt` file.
    ```bash
    cd imagex
    pip install -r requirements.txt
    ```

3.  **Restart ComfyUI**:
    Restart your ComfyUI instance to load the new custom nodes.

## Configuration

All configuration is managed through **environment variables**. This is the most secure and flexible way to configure the nodes, especially in containerized environments.

### Required Environment Variables

| Variable | Description | Example                                                                    |
| :--- | :--- |:---------------------------------------------------------------------------|
| `SQS_QUEUE_URL` | The full URL of the SQS queue where `Imagex` sends new jobs. The worker will not start if this is not set. | `https://sqs.us-east-2.amazonaws.com/.../imagex-job-submission-queue.fifo` |
| `AWS_REGION` | The AWS region for all services (SQS and S3). | `us-east-2`                                                                |
| `AWS_ACCESS_KEY_ID` | Your AWS access key. **(Recommended only for local development)**. | `XXXXXXXXXXXX`                                                     |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key. **(Recommended only for local development)**. | `XXXXXXXXXXXX`                                                             |

### Optional Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `COMFYUI_URL` | The URL of the local ComfyUI API endpoint. | `http://127.0.0.1:8188` |
| `SQS_POLL_WAIT_TIME` | The duration (in seconds) for SQS long polling. | `20` |
| `SQS_MAX_MESSAGES` | The maximum number of messages to fetch in a single poll. | `1` |

**Security Note**: For production environments, it is **highly recommended** to use IAM Roles (e.g., an EC2 instance profile or an ECS task role) instead of hardcoding AWS credentials as environment variables. The nodes are designed to automatically use IAM roles if available.

## Nodes Overview

You will find the nodes in your ComfyUI menu under the **Imagex/AWS** category.

### 1. Imagex S3 Uploader
-   **Description**: Securely uploads a generated image to a precise S3 path (`full_object_key`) provided by the `Imagex` backend.
-   **Inputs**: `images`, `bucket_name`, `full_object_key`, `region_name`.
-   **Output**: The `s3_url` of the uploaded file (e.g., `s3://my-bucket/path/to/image.png`).

### 2. Imagex Job Completion Notifier
-   **Description**: Sends a structured JSON message to the SQS completion queue, signaling that the job has finished successfully.
-   **Inputs**: `s3_url` (from the uploader), `job_id`, `completion_queue_url`, `region_name`.

### 3. Imagex SQS Worker Status
-   **Description**: A simple utility node that displays the current status of the background SQS worker thread. It confirms whether the listener is running and configured correctly.

## Example Workflow

This diagram shows the intended data flow between the custom nodes. The `job_id`, `bucket_name`, etc., are injected into the workflow by the `Imagex` backend when the job is created.

```mermaid
graph TD
    subgraph "ComfyUI Workflow"
        KSampler["fa:fa-image KSampler"] --> S3Uploader["Imagex S3 Uploader"];
        S3Uploader -- s3_url --> Notifier["Imagex Job Completion Notifier"];
    end

    style KSampler fill:#223,stroke:#88d
    style S3Uploader fill:#322,stroke:#d88
    style Notifier fill:#232,stroke:#8d8
