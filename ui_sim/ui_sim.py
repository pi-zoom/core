import zmq
import sys
import threading

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://localhost:9955")


subsocket = context.socket(zmq.SUB)
subsocket.connect ("tcp://localhost:9956")
subsocket.setsockopt_string(zmq.SUBSCRIBE, "")
def start_sub():
    try:
        print("SUB listening")
        while True:
            string = subsocket.recv_string()
            print(f"RX from core: {string}")
    except Exception as error:
        print(f"Error: {error}")


sub_thread = threading.Thread(target=start_sub)
sub_thread.start()

key = None
while key != "q":
    key = input("enter a command: ")
    if key == "a":
        msg = "looper get_input_gain"
        socket.send_string(msg)
        print("Sent:", msg)

    elif key == "r":
        msg = "looper register_update"
        socket.send_string(msg)
    elif key == "u":
        msg = "looper unregister_update"
        socket.send_string(msg)