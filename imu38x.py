import math
import serial
import serial.tools.list_ports

packet_header = bytearray.fromhex('5555')
# A2 packet
a2_size = 37
a2_header = bytearray.fromhex('4132')
# S0 packet
s0_size = 37
s0_header = bytearray.fromhex('5330')

class imu38x:
    def __init__(self, port, baud=115200, packet_type='a2', pipe=None):
        '''Initialize and then start ports search and autobaud process
        '''
        self.port = port
        self.baud = baud
        self.ser = serial.Serial(self.port, self.baud)
        self.open = self.ser.isOpen()
        self.latest = []
        self.ready = False
        self.pipe = pipe
        # self.header = a2_header     # packet type hex, default a2
        self.size = a2_size  # packet size, default a2 size
        if packet_type.lower() == 'a2':
            pass
        elif packet_type.lower() == 's0':
            # self.header = s0_header
            self.size = s0_size
        else:
            print('Unsupported packet type: %s'% packet_type)

    def start(self):
        if self.open:
            bf = bytearray(self.size*2)
            n_bytes = 0
            while True:
                data = self.ser.read(self.size)
                ## parse new
                n = len(data)
                for i in range(n):
                    bf[n_bytes + i] = data[i]
                n_bytes += n
                while n_bytes >= self.size:
                    if bf[0] == 0x55 and bf[1] == 0x55:
                        # crc
                        packet_crc = 256 * bf[self.size-2] + bf[self.size-1]
                        calculated_crc = calc_crc(bf[2:bf[4]+5])
                        # decode
                        if packet_crc == calculated_crc:
                            self.latest = parse_packet(bf[2:bf[4]+5])
                            # print(self.latest)
                            if self.pipe is not None:
                                self.pipe.send(self.latest)
                            # remove decoded data from the buffer
                            n_bytes -= self.size
                            for i in range(n_bytes):
                                bf[i] = bf[i+self.size]
                        else:
                            print('crc fail')
                            n_bytes = sync_packet(bf, n_bytes, packet_header)
                    else:
                        n_bytes = sync_packet(bf, n_bytes, packet_header)
    def get_latest(self):
        return self.latest

def parse_packet(payload):
    '''
    parse packet
    '''
    data = None
    if payload[0] == a2_header[0] and payload[1] == a2_header[1]:
        data = parse_A2(payload[3::])
    elif payload[0] == s0_header[0] and payload[1] == s0_header[1]:
        data = parse_S0(payload[3::])
    else:
        print('Unsupported packet type: %s'% payload[0:2])
    return data

def parse_S0(payload):
    '''S0 Payload Contents
    Byte Offset	Name	Format	Scaling	Units	Description
    0	xAccel	    I2	20/2^16	G	X accelerometer
    2	yAccel	    I2	20/2^16	G	Y accelerometer
    4	zAccel	    I2	20/2^16	G	Z accelerometer
    6	xRate   	I2	7*pi/2^16 [1260 deg/2^16]	rad/s [deg/sec]	X angular rate
    8	yRate	    I2	7*pi/2^16 [1260 deg/2^16]	rad/s [deg/sec]	Y angular rate
    10	zRate	    I2	7*pi/2^16 [1260 deg/2^16]	rad/s [deg/sec]	Z angular rate
    12	xMag	    I2	2/2^16	Gauss	X magnetometer
    14	yMag	    I2	2/2^16	Gauss	Y magnetometer
    16	zMag	    I2	2/2^16	Gauss	Z magnetometer
    18	xRateTemp	I2	200/2^16	deg. C	X rate temperature
    20	yRateTemp	I2	200/2^16	deg. C	Y rate temperature
    22	zRateTemp	I2	200/2^16	deg. C	Z rate temperature
    24	boardTemp	I2	200/2^16	deg. C	CPU board temperature
    26	GPSITOW	    U2	truncated	Ms	GPS ITOW (lower 2 bytes)
    28	BITstatus   U2 Master BIT and Status'''
    
    accels = [0 for x in range(3)] 
    for i in range(3):
        accel_int16 = (256 * payload[2*i] + payload[2*i+1]) - 65535 if 256 * payload[2*i] + payload[2*i+1] > 32767  else  256 * payload[2*i] + payload[2*i+1]
        accels[i] = (9.80665 * 20 * accel_int16) / math.pow(2,16)

    gyros = [0 for x in range(3)] 
    for i in range(3):
        gyro_int16 = (256 * payload[2*i+6] + payload[2*i+7]) - 65535 if 256 * payload[2*i+6] + payload[2*i+7] > 32767  else  256 * payload[2*i+6] + payload[2*i+7]
        gyros[i] = (1260 * gyro_int16) / math.pow(2,16) 

    mags = [0 for x in range(3)] 
    for i in range(3):
        mag_int16 = (256 * payload[2*i+12] + payload[2*i+13]) - 65535 if 256 * payload[2*i+12] + payload[2*i+13] > 32767  else  256 * payload[2*i+12] + payload[2*i+13]
        mags[i] = (2 * mag_int16) / math.pow(2,16) 

    temps = [0 for x in range(4)] 
    for i in range(4):
        temp_int16 = (256 * payload[2*i+18] + payload[2*i+19]) - 65535 if 256 * payload[2*i+18] + payload[2*i+19] > 32767  else  256 * payload[2*i+18] + payload[2*i+19]
        temps[i] = (200 * temp_int16) / math.pow(2,16)

    # Counter Value
    itow = 256 * payload[26] + payload[27]   

    # BIT Value
    bit = 256 * payload[28] + payload[29]

    return itow, accels, gyros, mags, temps, bit 

def parse_A2(payload):
    '''A2 Payload Contents
    0	rollAngle	I2	2*pi/2^16 [360 deg/2^16]	Radians [deg]	Roll angle
    2	pitchAngle	I2	2*pi/2^16 [360 deg/2^16]	Radians [deg]	Pitch angle
    4	yawAngleMag	I2	2*pi/2^16 [360 deg/2^16]	Radians [deg]	Yaw angle (magnetic north)
    6	xRateCorrected	I2	7*pi/2^16[1260 deg/2^16]	rad/s  [deg/sec]	X angular rate Corrected
    8	yRateCorrected	I2	7*pi/2^16 [1260 deg/2^16]	rad/s  [deg/sec]	Y angular rate Corrected
    10	zRateCorrected	I2	7*pi/2^16 [1260 deg/2^16]	rad/s  [deg/sec]	Z angular rate Corrected
    12	xAccel	  I2	20/2^16	g	X accelerometer
    14	yAccel	  I2	20/2^16	g	Y accelerometer
    16	zAccel	  I2	20/2^16	g	Z accelerometer
    18	xRateTemp I2	200/2^16	Deg.C   X rate temperature 
    20	yRatetemp I2	200/2^16	Deg.C	Y rate temperature 
    22	zRateTemp I2	200/2^16	Deg.C   Z rate temperature 
    24	timeITOW	U4	1	ms	DMU ITOW (sync to GPS)
    28	BITstatus	U2	-	-	Master BIT and Status'''

    angles = [0 for x in range(3)] 
    for i in range(3):
        angle_int16 = (256 * payload[2*i] + payload[2*i+1]) - 65535 if 256 * payload[2*i] + payload[2*i+1] > 32767  else  256 * payload[2*i] + payload[2*i+1]
        angles[i] = (360.0 * angle_int16) / math.pow(2,16) 

    gyros = [0 for x in range(3)] 
    for i in range(3):
        gyro_int16 = (256 * payload[2*i+6] + payload[2*i+7]) - 65535 if 256 * payload[2*i+6] + payload[2*i+7] > 32767  else  256 * payload[2*i+6] + payload[2*i+7]
        gyros[i] = (1260 * gyro_int16) / math.pow(2,16) 

    accels = [0 for x in range(3)] 
    for i in range(3):
        accel_int16 = (256 * payload[2*i+12] + payload[2*i+13]) - 65535 if 256 * payload[2*i+12] + payload[2*i+13] > 32767  else  256 * payload[2*i+12] + payload[2*i+13]
        accels[i] = (9.80665 * 20 * accel_int16) / math.pow(2,16)

    temp = [0 for x in range(3)] 
    for i in range(3):
        temp_int16 = (256 * payload[2*i+18] + payload[2*i+19]) - 65535 if 256 * payload[2*i+18] + payload[2*i+19] > 32767  else  256 * payload[2*i+18] + payload[2*i+19]
        temp[i] = (200 * temp_int16) / math.pow(2,16)

    # Counter Value
    itow = 16777216 * payload[24] + 65536 * payload[25] + 256 * payload[26] + payload[27]   

    # BIT Value
    bit = 256 * payload[28] + payload[29]

    return angles, gyros, accels, temp, itow, bit

def sync_packet(bf, bf_len, header):
    idx = bf.find(header[0], 0, bf_len) 
    if idx > 0 and bf[idx+1] == header[1]:
        bf_len = bf_len - idx
        for i in range(bf_len):
            bf[i] = bf[i+idx]
    else:
        bf_len = 0
    return bf_len

def calc_crc(payload):
    '''Calculates CRC per 380 manual
    '''
    crc = 0x1D0F
    for bytedata in payload:
        crc = crc^(bytedata << 8) 
        for i in range(0,8):
            if crc & 0x8000:
                crc = (crc << 1)^0x1021
            else:
                crc = crc << 1

    crc = crc & 0xffff
    return crc

if __name__ == "__main__":
    port = 'COM11'
    baud = 115200
    unit = imu38x(port, baud, packet_type='a2', pipe=None)
    unit.start()
