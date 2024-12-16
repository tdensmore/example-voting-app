import pytest
import requests
from testcontainers.redis import RedisContainer
from testcontainers.core.container import DockerContainer
import json
import time

class VoteAppContainer(DockerContainer):
    def __init__(self, redis_host, redis_port):
        super(VoteAppContainer, self).__init__("example-voting-app-vote")
        self.with_env("REDIS_HOST", redis_host)
        self.with_env("REDIS_PORT", str(redis_port))
        self.with_exposed_ports(80)

@pytest.fixture(scope="function")
def vote_app_environment():
    # Start Redis container
    with RedisContainer() as redis:
        # Build the vote app image
        import subprocess
        subprocess.run(["docker", "build", "-t", "example-voting-app-vote", "."], check=True)
        
        # Start vote app container
        with VoteAppContainer(
            redis_host=redis.get_container_host_ip(),
            redis_port=redis.get_exposed_port(6379)
        ) as vote_app:
            # Wait for the application to be ready
            time.sleep(2)
            vote_app_url = f"http://{vote_app.get_container_host_ip()}:{vote_app.get_exposed_port(80)}"
            
            yield {
                "vote_app_url": vote_app_url,
                "redis": redis
            }

def test_vote_submission(vote_app_environment):
    # Get the URL where the vote app is running
    vote_app_url = vote_app_environment["vote_app_url"]
    
    # First request to get the cookie
    response = requests.get(vote_app_url)
    assert response.status_code == 200
    cookies = response.cookies
    
    # Submit a vote
    vote_data = {"vote": "a"}
    response = requests.post(vote_app_url, data=vote_data, cookies=cookies)
    assert response.status_code == 200
    
    # Verify vote was stored in Redis
    redis = vote_app_environment["redis"]
    redis_client = redis.get_client()
    votes = redis_client.lrange("votes", 0, -1)
    
    # There should be at least one vote
    assert len(votes) > 0
    
    # Parse the latest vote
    latest_vote = json.loads(votes[-1])
    assert "vote" in latest_vote
    assert latest_vote["vote"] == "a"

def test_options_displayed(vote_app_environment):
    # Get the URL where the vote app is running
    vote_app_url = vote_app_environment["vote_app_url"]
    
    # Get the main page
    response = requests.get(vote_app_url)
    assert response.status_code == 200
    
    # Check if both options are in the response
    content = response.text
    assert "Cats" in content
    assert "Dogs" in content
