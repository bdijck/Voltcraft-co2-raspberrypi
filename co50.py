import RPi.GPIO as GPIO
import time
import json
from datetime import datetime
from datetime import timedelta
from ftplib import FTP
import ftplib

def setupGPIO():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(20, GPIO.IN)
    GPIO.setup(21, GPIO.IN)


def main():
    setupGPIO()
    readPinsInLoop() # like the name says, this will loop undefinitely


# list of 8 bits to one byte, e.g. [1,0,0,0,0,0,0,0] to 128 (MSB first)
def bitsToByte(bits):
    if len(bits) != 8:
        print("ERROR NOT 8 BITS")
        return None

    ret = 0

    for i in range(0,8):
        ret = ret + (bits[i] << (7 - i))

    return ret

# simple conversion from Kelvin to Celcius
def temp_K_to_C(temp_K):
    return temp_K - 273.15


# analyse a 5-byte frame; temperature, CO2 PPM and relative humidity are supported
# other frame types can be added easily
def analyzeFrameData(dicData, B1, B2, B3, B4, B5):

    # temperature
    if B1 == 0x42:  # example: 46 1a 84 e4 0d
        temp_raw = ((B2 << 8 ) + B3) 
        temp_C = temp_K_to_C(temp_raw / 16.0)
        print ("  --> {:02X} temp = {} ".format(B1, temp_C))
        dicData["TEMPERATURE_CELCIUS"] = temp_C
        
    # CO2 PPM
    if B1 == 0x50:
        ppm = ((B2 << 8 ) + B3)
        print ("  --> {:02X} CO2 PPM: {}".format(B1, ppm))
        dicData["CO2_CONCENTRATION_PPM"] = ppm

    # RELATIVE HUMIDITY
    if B1 == 0x41:
        relhum = ((B2 << 8 ) + B3) / 100.0
        print ("  --> {:02X} Rel. hum.: {}".format(B1, relhum))
        dicData["RELATIVE_HUMIDITY"] = relhum

    # INSERT OTHER FRAME TYPES HERE


# chops up the frame in 5 bytes
def processFrame(frame, dicData):
    if len(frame) != 40: # we expect 40
        #print ("dropping frame of {} length ({} expected)".format(len(frame), expected_frame_length))
        pass
    else:
        B1 = bitsToByte(frame[0:8])
        B2 = bitsToByte(frame[8:16])
        B3 = bitsToByte(frame[16:24])
        B4 = bitsToByte(frame[24:32])
        B5 = bitsToByte(frame[32:40])
        #print ("Frame: {:02X} {:02X} {:02X} {:02X} {:02X} ".format(B1, B2, B3, B4, B5))
        analyzeFrameData(dicData, B1, B2, B3, B4, B5)

# Takes sample timings (timespans between readings) and the binary data
# Returns tuple consisting of timestamp and a dictionary of data,
# e.g. ('11/29/2018 20:49:49.540945', {'CO2_CONCENTRATION_PPM': 792, 'TEMPERATURE_CELCIUS': 21.225000000000023})
def processSamplingData(clock_signal_cycle_timings, bits_read_buffer):
    print("Start processing sampling data...")

    dicData = {} # dictionary will contain parameter & value

    threshold = 0.050 # 50 ms
    frame = []
    resetFrame = False # to cut the data into frames

    for i in range(len(bits_read_buffer)):
        if clock_signal_cycle_timings[i] > threshold:
            resetFrame = True

        if resetFrame == True:
            processFrame(frame, dicData)
            frame = []
            resetFrame = False

        frame.append(bits_read_buffer[i])

    print("Done processing sampling data!")

    # we use the same timestamp (now) for all data of the same sample session (!)
    timestamp = datetime.utcnow().strftime("%m/%d/%Y %H:%M:%S.%f")
    return (timestamp, dicData)
    

def readPinsInLoop():
    # only used for counting and logging the number of sessions
    session_counter = 0   
    session_comms_failure_counter = 0

    clock_signal_cycle_timings = []             # list of timespans (time between reading X and reading X-1); used to detect frame reset
    last_time = time.clock()                    # used to calculate timespans
    last_clock_signal = None                    # used to detect clock signal change
    bits_read_buffer = []                       # contains the data that is read (bits)
    last_sampling_timestamp = datetime.now()    # used to calculate when next sampling session will start
    
    print ("Start sampling the CO-50 device for a while...")
    while True:        
        current_clock_signal = GPIO.input(21)
        if current_clock_signal == last_clock_signal:
            pass
        else: # change!

            if current_clock_signal == 0:
                now_time = time.clock()
                clock_signal_cycle_timings.append(now_time - last_time)
                last_time = now_time

                bit = GPIO.input(20)
                bits_read_buffer.append(bit)

                # we take a good amount of time to sample to make sure we have what we need
                # so the next block will only be executed once we have enough data
                if len(clock_signal_cycle_timings) >= 1000:
                    processedSamplingData = processSamplingData(clock_signal_cycle_timings, bits_read_buffer)
                    clock_signal_cycle_timings = []
                    bits_read_buffer = []

                    uploadResultOK = uploadData(processedSamplingData)
                    if (uploadResultOK == False):
                        session_comms_failure_counter += 1
                    session_counter += 1
                    print ("I have done {} sessions so far (comms failures: {}).".format(session_counter, session_comms_failure_counter))

                    # wait a while till we start again
                    time_taken = datetime.now() - last_sampling_timestamp
                    print("last session took {}, started at {}.".format(time_taken, last_sampling_timestamp))  

                    next_sampling_start_timestamp = last_sampling_timestamp + timedelta(seconds=40) #timedelta(seconds=5*60)

                    print("Waiting for next sampling session start... (next session should start at {})".format(next_sampling_start_timestamp))
                    while (datetime.now() < next_sampling_start_timestamp):
                        #print ("z {} {}".format(datetime.now(), next_sampling_start_timestamp))
                        time.sleep(1)

                    print ("Start sampling for a while again...")
                    last_sampling_timestamp = datetime.now()

            last_clock_signal = current_clock_signal

# Originally, this function uploaded data to some online data analysis platform.
# Now it just outputs to the screen.
def uploadData(sessionData):
    
    # screen output
    for k in sessionData[1]:
        timestamp = sessionData[0]
        param = k
        value = sessionData[1][k]
        print ("{}: {} -> {}".format(timestamp, param, value))

    resultOK = True # insert whatever you want to do with the data here
    return resultOK

if __name__ == '__main__':
    main()
