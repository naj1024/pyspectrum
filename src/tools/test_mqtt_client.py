import time

import paho.mqtt.client as mqtt  # import the client1


def on_message(client, user_data, message):
    print(message.topic, str(message.payload.decode("utf-8")))


broker_address = "power"
root_topic = "spectrum"

mqtt_client = mqtt.Client("P1")  # create new instance
mqtt_client.on_message = on_message  # attach function to callback
print("connecting to broker", broker_address)
try:
    mqtt_client.connect(broker_address)  # connect to broker
except OSError as msg:
    print("Error:", msg)
    raise

print("connected to", broker_address)

mqtt_client.loop_start()  # start the loop
print("subscribing to topic:", root_topic)
mqtt_client.subscribe(f"{root_topic}/#")

while True:
    time.sleep(0.1)
