#
#  Created by A. Kevin Bailey on 8/10/2024 under a GPL3.0 license
#
import os
import sys
import threading
import time

import requests
import urllib3
from requests.adapters import HTTPAdapter


def print_help():
    print("Usage:")
    print("  python3 api-tester.py [URL] [arguments]")
    print("Required arguments:")
    print("  [URL]                   - Server URL.")
    print("Optional arguments:")
    print("  -totalCalls [value]     - Total number of calls across all threads. Default is 10000.")
    print("  -numThreads [value]     - Number of threads. Default is 12.")
    print("  -sleepTime [value]      - Sleep time in milliseconds between calls within a thread. Default is 0")
    print("  -requestTimeOut [value] - HTTP request timeout in milliseconds. Default is 10000.")
    print("  -connectTimeOut [value] - HTTP request timeout in milliseconds. Default is 20000.")
    print("  -reuseConnects          - Attempts to reuse the connections if the server allows it.")
    print("  -keepConnectsOpen       - Force a new connection with every request (not advised).")
    print("Help:")
    print("  -? or --help            - Display this help message.")


# Function to make the GET request and measure response time
def fetch_data(print_lock, session, response_times, url, sleep_time, keep_connects_open, reuse_connects, thread_id,
               num_calls, request_time_out, connect_time_out):
    for call_num in range(num_calls):
        timeout_tuple = (request_time_out, connect_time_out)
        headers_struct = {"Connection": "keep-alive"} if reuse_connects else {"Connection": "close"}
        call_start_time = time.time()
        try:
            response = session.get(url, headers=headers_struct, timeout=timeout_tuple, stream=False)
            call_end_time = time.time()
            response_time = (call_end_time - call_start_time) * 1000  # Convert to millisecond

            if not keep_connects_open:
                # Must read the body to close the session.  Dumping it to null out.
                # Not reading the body will keep the connection occupied until the connection timeout.
                f = open(os.devnull, "w")
                f.write(response.content.decode("utf-8"))
                f.close()

            with print_lock:
                if response.status_code == 200:
                    print(f"Thread {thread_id:>2}.{call_num:<6} - Success: {response.status_code}"
                          f" - Response time: {response_time:.2f} ms")
                else:
                    print(
                        f"Thread {thread_id:>2}.{call_num:<6} - Failed with status code: {response.status_code}"
                        f" - Response time: {response_time:.2f} ms")
                response_times.append(response_time)
        except requests.exceptions.RequestException as e:
            error_end_time = time.time()
            response_time = (error_end_time - call_start_time) * 1000  # Convert to milliseconds
            with print_lock:
                print(f"Thread {thread_id:>2}.{call_num:<6} - Request failed: {e} - Response time:"
                      f" {response_time:.2f} ms")
                response_times.append(response_time)
        time.sleep(sleep_time)


def main():
    # Total number of calls to make
    total_calls = 10000
    # Number of threads
    num_threads = 16
    # Delay between calls in seconds
    sleep_time = 0.0
    # HTTP request timeout in seconds
    request_time_out = 10.0
    # HTTP connection timeout in seconds
    connect_time_out = request_time_out * 3
    # Add the request 'Connection: keep-alive' header
    reuse_connects = False
    # Leaves all the connection requests open
    keep_connects_open = False
    # List to store response times
    response_times = []
    # Lock for thread-safe print and data access
    print_lock = threading.Lock()

    # Check if there are any arguments
    if len(sys.argv) < 2:
        print("Error: Not enough arguments provided.")
        print_help()
        return

    # Check for help flags
    if sys.argv[1] in ("-?", "--help"):
        print_help()
        return

    # Make sure that there is a URL
    if sys.argv[1].startswith("http"):
        url = sys.argv[1]
    else:
        print("Error: [URL] must be the first parameter.")
        print_help()
        return

    # Parse command line arguments
    args = sys.argv[2:]
    for i in range(0, len(args), 2):
        if args[i] == "-totalCalls":
            try:
                total_calls = int(args[i+1])
            except (ValueError, IndexError):
                print("Error: -totalCalls must be followed by an integer.")
                return
        elif args[i] == "-numThreads":
            try:
                num_threads = int(args[i+1])
            except (ValueError, IndexError):
                print("Error: -numThreads must be followed by an integer.")
                return
        elif args[i] == "-sleepTime":
            try:
                sleep_time = float(args[i+1]) / 1000
            except (ValueError, IndexError):
                print("Error: -sleepTime must be followed by an integer.")
                return
        elif args[i] == "-requestTimeOut":
            try:
                request_time_out = float(args[i+1]) / 1000
            except (ValueError, IndexError):
                print("Error: -requestTimeOut must be followed by an integer.")
                return
        elif args[i] == "-connectTimeOut":
            try:
                connect_time_out = float(args[i + 1]) / 1000
            except (ValueError, IndexError):
                print("Error: -connectTimeOut must be followed by an integer.")
                return
        elif args[i] == "-reuseConnects":
            reuse_connects = True

        elif args[i] == "-keepConnectsOpen":
            keep_connects_open = True

    # Calculate the number of calls each thread should make
    calls_per_thread = total_calls // num_threads
    remainder_calls = total_calls % num_threads

    # List to hold the threads
    threads = []

    # Set up the HTTP session for connection reuse
    client_session = requests.session()
    http_adapter = HTTPAdapter(pool_connections=num_threads, pool_maxsize=num_threads * 10, max_retries=5)
    if url.lower().startswith("https"):
        client_session.mount("https://", http_adapter)
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    else:
        client_session.mount("http://", http_adapter)

    # Capture start time
    start_time = time.time()

    # Create and start threads
    for i in range(num_threads):
        # Determine the number of calls for this thread
        # Add one call to each thread number that is less than the mod of the total calls to compensate for the remainder
        num_calls_this_thread = calls_per_thread + (1 if i < remainder_calls else 0)

        thread = threading.Thread(target=fetch_data, args=(
            print_lock, client_session, response_times, url, sleep_time, keep_connects_open, reuse_connects, i,
            num_calls_this_thread, request_time_out, connect_time_out))
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    # Capture end time and calculate total time
    end_time = time.time()
    total_time = end_time - start_time
    # Calculate requests per second
    requests_per_second = total_calls / total_time
    # Calculate and print the average response time
    if response_times:
        average_response_time = sum(response_times) / len(response_times)
    else:
        average_response_time = 0

    print(f"Total thread count: {num_threads}")
    print(f"Total test time: {total_time:.2f} s")
    print(f"Average response time: {average_response_time:.2f} ms")
    print(f"Average requests per second: {requests_per_second:.2f}")

    # Dump all the connection states
    http_adapter.close()
    print("All threads have finished.")


if __name__ == "__main__":
    main()
