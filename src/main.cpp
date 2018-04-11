/**
 * Copyright (c) 2017, Arm Limited and affiliates.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#include "mbed.h"
#include "LoRaWANInterface.h"
#include "trace_helper.h"
#include "lora_radio_helper.h"
#include "CayenneLPP.h"
#include "DHT11.h"

// EventQueue to dispatch events around - https://os.mbed.com/docs/latest/tutorials/the-eventqueue-api.html
static EventQueue ev_queue(16 * EVENTS_EVENT_SIZE);

// Forward declaration of the event handler
static void lora_event_handler(lorawan_event_t event);

// Pointer to stack
static LoRaWANInterface* lorawan = NULL;

// Application specific callbacks
static lorawan_app_callbacks_t callbacks;

int main(void) {
    // Constructing Mbed LoRaWANInterface and passing it down the radio object
    LoRaWANInterface lora(get_lora_radio());
    lorawan = &lora;

    // setup tracing (you can enable this in mbed_app.json)
    setup_trace();

    // Initialize LoRaWAN stack
    if (lorawan->initialize(&ev_queue) != LORAWAN_STATUS_OK) {
        printf("LoRa initialization failed!\r\n");
        return -1;
    }

    printf("LoRaWAN stack initialized\r\n");

    // prepare application callbacks
    callbacks.events = mbed::callback(lora_event_handler);
    lorawan->add_app_callbacks(&callbacks);

    lorawan_status_t retcode = lorawan->connect();

    if (retcode == LORAWAN_STATUS_OK ||
        retcode == LORAWAN_STATUS_CONNECT_IN_PROGRESS) {
    } else {
        printf("Connection error, code = %d\r\n", retcode);
        return -1;
    }

    printf("Connection - In Progress ...\r\n");

    // make your event queue dispatching events forever
    // optionally: run this in a separate thread
    ev_queue.dispatch_forever();
}

/**
 * Sends a message to the Network Server
 */
static void send_message() {
#if MBED_CONF_APP_REAL_SENSOR == 1
    static Dht11 sensor(SPI_MISO);
    int r = sensor.read();
    if (r != DHTLIB_OK) {
        printf("Reading sensor value failed... %d\r\n", r);
        return;
    }

    float sensor_value = sensor.getCelsius();
#else
    float sensor_value = (float)rand() / (float)(RAND_MAX / 20.0f);
#endif

    // transmission payload, max 50 bytes in size
    CayenneLPP payload(50);
    // 10=channel, Cayenne-LPP works with channels to identify different sensors. If a sensor value did not change, just don't add it to the payload...
    payload.addTemperature(10, sensor_value);

    printf("Sensor value is %.2f\r\n", sensor_value);

    int16_t retcode = lorawan->send(MBED_CONF_LORA_APP_PORT, payload.getBuffer(), payload.getSize(), MSG_UNCONFIRMED_FLAG);

    if (retcode < 0) {
        retcode == LORAWAN_STATUS_WOULD_BLOCK ? printf("send - WOULD BLOCK - Duty cycle violation?\r\n")
                : printf("send() - Error code %d\r\n", retcode);
        return;
    }

    printf("%d bytes scheduled for transmission\r\n", retcode);
}

/**
 * Receive a message from the network on port MBED_CONF_LORA_APP_PORT (port 15)
 */
static void receive_message() {
    uint8_t rx_buffer[LORAMAC_PHY_MAXPAYLOAD] = { 0 };

    int16_t retcode = lorawan->receive(MBED_CONF_LORA_APP_PORT, rx_buffer,
                              LORAMAC_PHY_MAXPAYLOAD,
                              MSG_CONFIRMED_FLAG|MSG_UNCONFIRMED_FLAG);

    if (retcode < 0) {
        printf("receive() - Error code %d\r\n", retcode);
        return;
    }

    printf("Received data (length=%d): ", retcode);

    for (uint8_t i = 0; i < retcode; i++) {
        printf("%x", rx_buffer[i]);
    }

    printf("\r\n");
}

/**
 * Event handler
 */
static void lora_event_handler(lorawan_event_t event)
{
    switch (event) {
        case CONNECTED:
            printf("Connection - Successful\r\n");
            ev_queue.call_every(10000, send_message);

            break;
        case DISCONNECTED:
            ev_queue.break_dispatch();
            printf("Disconnected Successfully\r\n");
            break;
        case TX_DONE:
            printf("Message Sent to Network Server\r\n");
            break;
        case TX_TIMEOUT:
        case TX_ERROR:
        case TX_CRYPTO_ERROR:
        case TX_SCHEDULING_ERROR:
            printf("Transmission Error - EventCode = %d\r\n", event);
            break;
        case RX_DONE:
            printf("Received message from Network Server\r\n");
            receive_message();
            break;
        case RX_TIMEOUT:
        case RX_ERROR:
            printf("Error in reception - Code = %d\r\n", event);
            break;
        case JOIN_FAILURE:
            printf("OTAA Failed - Check Keys\r\n");
            break;
        default:
            MBED_ASSERT("Unknown Event");
    }
}
