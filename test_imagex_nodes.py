# File: test_imagex_nodes.py

import pytest
import json
import requests
import numpy as np
from unittest.mock import MagicMock
from botocore.exceptions import ClientError, NoCredentialsError

# Import classes from the __init__.py file where they are defined
from __init__ import ImagexS3Uploader, ImagexJobCompleteNotifier, SQSWorker, logger

# Disable logging during tests to keep the output clean
logger.setLevel("CRITICAL")

# --- Pytest Fixtures ---

@pytest.fixture
def mock_boto_client(mocker):
    """A generic fixture to mock boto3.client for AWS services."""
    return mocker.patch('boto3.client')

@pytest.fixture
def mock_requests_post(mocker):
    """A fixture to mock the requests library's post method."""
    return mocker.patch('requests.Session.post')

@pytest.fixture
def mock_image_tensor():
    """A fixture to create a mock image tensor."""
    tensor = MagicMock()
    fake_image_array = np.zeros((64, 64, 3), dtype=np.float32)
    tensor.cpu.return_value.numpy.return_value = fake_image_array
    return tensor

# --- Tests for ImagexS3Uploader ---

class TestImagexS3Uploader:
    """Unit tests for the ImagexS3Uploader node."""

    def test_upload_to_s3_succeeds_on_valid_input(self, mock_boto_client, mock_image_tensor):
        """Verify that a successful upload calls the S3 client and returns the correct URL."""
        mock_s3_instance = MagicMock()
        mock_boto_client.return_value = mock_s3_instance
        uploader = ImagexS3Uploader()

        result = uploader.upload_to_s3([mock_image_tensor], "test-bucket", "path/to/image.png", "us-east-1")

        mock_s3_instance.upload_fileobj.assert_called_once()
        assert result == ("s3://test-bucket/path/to/image.png",), "Should return the correct S3 URL"

    def test_upload_to_s3_returns_empty_on_client_error(self, mock_boto_client, mock_image_tensor):
        """Verify that an empty string tuple is returned when the S3 client raises an error."""
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload_fileobj.side_effect = ClientError({}, "UploadObject")
        mock_boto_client.return_value = mock_s3_instance
        uploader = ImagexS3Uploader()

        result = uploader.upload_to_s3([mock_image_tensor], "test-bucket", "path/to/image.png", "us-east-1")

        assert result == ("",), "Should return an empty string tuple on upload failure"

    def test_upload_to_s3_returns_empty_on_no_credentials(self, mock_boto_client):
        """Verify that an empty string tuple is returned if no AWS credentials are found."""
        mock_boto_client.side_effect = NoCredentialsError()
        uploader = ImagexS3Uploader()

        result = uploader.upload_to_s3([MagicMock()], "test-bucket", "path/to/image.png", "us-east-1")

        assert result == ("",), "Should return an empty string tuple when credentials are not configured"

# --- Tests for ImagexJobCompleteNotifier ---

class TestImagexJobCompleteNotifier:
    """Unit tests for the ImagexJobCompleteNotifier node."""

    def test_notify_completion_succeeds_on_valid_input(self, mock_boto_client):
        """Verify a successful notification calls the SQS client with the correct parameters."""
        mock_sqs_instance = MagicMock()
        mock_boto_client.return_value = mock_sqs_instance
        notifier = ImagexJobCompleteNotifier()

        notifier.notify_completion("s3://bucket/key.png", "job-123", "http://sqs-url", "us-east-1")

        mock_boto_client.assert_called_with('sqs', region_name="us-east-1")
        mock_sqs_instance.send_message.assert_called_once()

    def test_notify_completion_handles_client_error_gracefully(self, mock_boto_client):
        """Verify that the node does not crash when the SQS client raises an error."""
        mock_sqs_instance = MagicMock()
        mock_sqs_instance.send_message.side_effect = ClientError({}, "SendMessage")
        mock_boto_client.return_value = mock_sqs_instance
        notifier = ImagexJobCompleteNotifier()

        # This call should not raise an exception
        notifier.notify_completion("s3://bucket/key.png", "job-123", "http://sqs-url", "us-east-1")

        mock_sqs_instance.send_message.assert_called_once()

    def test_notify_completion_uses_fallback_for_malformed_s3_url(self, mock_boto_client):
        """Verify that a malformed S3 URL is used as a fallback in the notification message."""
        mock_sqs_instance = MagicMock()
        mock_boto_client.return_value = mock_sqs_instance
        notifier = ImagexJobCompleteNotifier()

        malformed_url = "s3:this-is-not-a-valid-url"
        notifier.notify_completion(malformed_url, "job-123", "http://sqs-url", "us-east-1")

        # Extract the MessageBody from the mock call and parse it
        message_body_str = mock_sqs_instance.send_message.call_args[1]['MessageBody']
        message_body = json.loads(message_body_str)

        assert message_body['imageUrl'] == malformed_url, "The original malformed URL should be used as a fallback"

# --- Tests for SQSWorker ---

@pytest.fixture
def sqs_worker(mock_boto_client):
    """A fixture to create a mocked SQSWorker instance for testing."""
    mock_sqs_instance = MagicMock()
    mock_boto_client.return_value = mock_sqs_instance

    worker = SQSWorker("http://sqs-url", "us-west-2", "http://comfy-api", 1, 1)
    worker.sqs = mock_sqs_instance # Override the client with our mock
    return worker

class TestSQSWorker:
    """Unit tests for the SQSWorker background process."""

    def test_process_message_succeeds_and_deletes_message(self, sqs_worker, mock_requests_post):
        """Verify that a valid message is processed and deleted from the queue."""
        workflow_payload = {"prompt": {"key": "value"}}
        message_envelope = {"metadata": {"jobId": "job-123"}, "payload": json.dumps(workflow_payload)}
        sqs_message = {"MessageId": "msg-1", "ReceiptHandle": "handle-1", "Body": json.dumps(message_envelope)}

        mock_requests_post.return_value.status_code = 200

        sqs_worker._process_message(sqs_message)

        mock_requests_post.assert_called_once()
        sqs_worker.sqs.delete_message.assert_called_with(QueueUrl="http://sqs-url", ReceiptHandle="handle-1")

    def test_process_message_deletes_poison_pill_on_key_error(self, sqs_worker):
        """Verify that a malformed message (missing keys) is deleted to prevent queue poisoning."""
        malformed_envelope = {"metadata": {"jobId": "job-123"}} # Missing "payload" key
        sqs_message = {"MessageId": "msg-2", "ReceiptHandle": "handle-2", "Body": json.dumps(malformed_envelope)}

        sqs_worker._process_message(sqs_message)

        sqs_worker.sqs.delete_message.assert_called_with(QueueUrl="http://sqs-url", ReceiptHandle="handle-2")

    def test_process_message_does_not_delete_on_comfyui_failure(self, sqs_worker, mock_requests_post):
        """Verify that the SQS message is NOT deleted if the ComfyUI API call fails, allowing for a retry."""
        mock_requests_post.side_effect = requests.exceptions.ConnectionError("API is down")

        workflow_payload = {"prompt": {}}
        message_envelope = {"metadata": {"jobId": "job-123"}, "payload": json.dumps(workflow_payload)}
        sqs_message = {"MessageId": "msg-3", "ReceiptHandle": "handle-3", "Body": json.dumps(message_envelope)}

        sqs_worker._process_message(sqs_message)

        sqs_worker.sqs.delete_message.assert_not_called()