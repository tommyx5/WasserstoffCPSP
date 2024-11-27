import threading

class StateManager:
    STATES = ['WAITING_FOR_RESSOURCES', 'PROCESSING_REQUESTS']

    def __init__(self, count_gen):
        self.lock = threading.Lock()
        self.count_gen = count_gen # number of ressources generators

        self.count = 0
        self.available_ressources = 0
        self.requests = [] # Request queue

    def reset_tick(self):
        """Resets available power and prepares for a new tick."""
        with self.lock:
            self.available_ressources = 0
            self.count = 0
            self.requests = []

    def add_power(self, ressources_to_add):
        """Adds power to the current tick and updates statistics."""
        with self.lock:
            if self.count % self.count_gen == 0:
                self.available_ressources = ressources_to_add
            else:
                self.available_ressources += ressources_to_add
            self.count += 1

    def add_request(self, topic, demand, timestamp):
        """Queues a power request."""
        with self.lock:
            self.requests.append((topic, demand, timestamp))

    def process_requests(self, mqtt_client):
        """Handles all pending requests after collecting power for the tick."""
        with self.lock:
            # Process queued requests
            for topic, demand, timestamp in self.requests:
                ressources_supplied = min(demand, self.available_ressources)
                self.available_ressources -= ressources_supplied

                response = {"powersupply": ressources_supplied, "timestamp": timestamp}
                mqtt_client.publish(topic, json.dumps(response))