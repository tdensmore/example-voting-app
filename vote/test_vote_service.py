import pytest
import requests
from testcontainers.redis import RedisContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
import json
import time

class VoteAppContainer(DockerContainer):
    """Custom container class for the voting application"""
    
    def __init__(self):
        # Use the same image name as in docker-compose
        super(VoteAppContainer, self).__init__("example-voting-app-vote:test")
        self.with_exposed_ports(80)
        self.with_env("FLASK_ENV", "development")
        
    def start(self):
        """Override start to wait for the application to be ready"""
        super().start()
        # Wait for Gunicorn to start
        wait_for_logs(self, "Listening at: http://0.0.0.0:80")
        return self

@pytest.fixture(scope="function")
def vote_app_environment():
    """Fixture that provides a complete voting app environment with Redis"""
    
    # Start Redis container
    with RedisContainer() as redis:
        redis_host = redis.get_container_host_ip()
        redis_port = redis.get_exposed_port(6379)
        
        # Build the vote app image
        import subprocess
        subprocess.run([
            "docker", "build", 
            "-t", "example-voting-app-vote:test",
            "-f", "Dockerfile",
            "--target", "dev",  # Use dev target for faster builds
            "."
        ], check=True)
        
        # Start vote app container
        with VoteAppContainer() as vote_app:
            # Configure Redis connection
            vote_app.with_env("REDIS_HOST", redis_host)
            vote_app.with_env("REDIS_PORT", str(redis_port))
            
            vote_app_url = f"http://{vote_app.get_container_host_ip()}:{vote_app.get_exposed_port(80)}"
            
            yield {
                "vote_app_url": vote_app_url,
                "redis": redis
            }

def test_vote_submission(vote_app_environment):
    """Test that votes can be submitted and are stored in Redis"""
    
    vote_app_url = vote_app_environment["vote_app_url"]
    
    # First request to get the cookie
    response = requests.get(vote_app_url)
    assert response.status_code == 200, "Failed to get initial page"
    cookies = response.cookies
    
    # Submit a vote
    vote_data = {"vote": "a"}
    response = requests.post(vote_app_url, data=vote_data, cookies=cookies)
    assert response.status_code == 200, "Failed to submit vote"
    
    # Verify vote was stored in Redis
    redis = vote_app_environment["redis"]
    redis_client = redis.get_client()
    
    # Wait for the vote to be processed (add retry logic)
    max_retries = 5
    for _ in range(max_retries):
        votes = redis_client.lrange("votes", 0, -1)
        if votes:
            break
        time.sleep(1)
    else:
        pytest.fail("Vote was not stored in Redis after multiple retries")
    
    # Parse the latest vote
    latest_vote = json.loads(votes[-1])
    assert "vote" in latest_vote, "Vote data is missing vote field"
    assert latest_vote["vote"] == "a", f"Expected vote 'a' but got {latest_vote['vote']}"

def test_options_displayed(vote_app_environment):
    """Test that voting options are correctly displayed"""
    
    vote_app_url = vote_app_environment["vote_app_url"]
    
    # Get the main page
    response = requests.get(vote_app_url)
    assert response.status_code == 200, "Failed to get voting page"
    
    # Check if both options are in the response
    content = response.text
    assert "Cats" in content, "Option 'Cats' not found in page"
    assert "Dogs" in content, "Option 'Dogs' not found in page"

def test_health_check(vote_app_environment):
    """Test the application's health check endpoint"""
    
    vote_app_url = vote_app_environment["vote_app_url"]
    
    # Make a request to the root endpoint
    response = requests.get(vote_app_url)
    assert response.status_code == 200, "Health check failed"
