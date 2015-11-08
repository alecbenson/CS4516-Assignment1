import socket
from struct import *
import random
import array
import select
import time
import sys
import math


class Pinger:

    def __init__(self):
        self.samples = []

    def checksum(self, pkt):
        # Pad odd length packets
        if len(pkt) % 2 != 0:
            pkt += "\x00"

        s = sum(array.array("H", pkt))
        s = (s & 0xFFFF) + (s >> 16)
        s = ~(s + (s >> 16))

        # Convert endianness
        shift = (s >> 8) & 0xFF
        return (shift | s << 8) & 0xFFFF

    def recv(self, s, p_id, start_time):
        # Wait until data is available or timeout occurs
        ready = select.select([s], [], [], 1)
        if ready[0]:
            recv_packet, addr = s.recvfrom(1024)

            elapsed = 1000 * (time.time() - start_time)
            ip = unpack('!BBHHHBBH4s4s', recv_packet[:20])
            icmp = unpack('bbHHh', recv_packet[20:28])
            bytes_recvd = len(recv_packet)

            print "{0} bytes from {1}: icmp seq={2} ttl={3} time={4}" \
                .format(bytes_recvd, addr[0], icmp[4], ip[5], elapsed)
            self.samples.append(Sample(elapsed, True))
        else:
            self.samples.append(Sample(1, False))
            print "Request timed out"

    def ping(self, dst, seq=0):
        # Convert the url to an IP
        try:
            dst_ip = socket.gethostbyname(dst)
        except socket.gaierror as e:
            print e
            return

        # Create the socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW,socket.IPPROTO_ICMP)
        except socket.error as e:
            print e
            return

        p_id = random.randint(0, 65535)
        packet = self.icmp(p_id, seq)
        start_time = time.time()
        sent = s.sendto(packet, (dst_ip, 1))
        self.recv(s, p_id, start_time)

    def icmp(self, p_id, seq=0):
        typ = 8
        code = 0

        # Create the header so that we can fill in the CRC
        header = pack('bbHHh', typ, code, 0, p_id, seq)
        payload = "A" * 36

        # Fill in the CRC for the packet
        crc = socket.htons(self.checksum(header + payload))
        header = pack('bbHHh', typ, code, crc, p_id, seq)
        return header + payload

    def ping_many(self, dst, count=0):
        try:
            if(count > 0):
                for i in range(count):
                    self.ping(dst, i)
                    time.sleep(1)
            else:
                seq = 0
                while True:
                    self.ping(dst, seq)
                    seq += 1
                    time.sleep(1)
        except KeyboardInterrupt:
            self.print_summary(dst)
            sys.exit()
        self.print_summary(dst)

    def print_summary(self, dst):
        full_summary = ""
        total_sent = len(self.samples)
        total_recvd = len([s for s in self.samples if s.received == True])

        num_lost = total_sent - total_recvd
        percent_lost = (1 - (total_recvd / float(total_sent))) * 100

        if(total_recvd > 0):
            rtt_samples = [s.rtt for s in self.samples if s.received == True]
            rtt_min = min(rtt_samples)
            rtt_max = max(rtt_samples)
            rtt_avg = sum(rtt_samples) / total_recvd

            rtt_avg_diff = map(lambda x: (x - rtt_avg)**2, rtt_samples)
            rtt_variance = sum(rtt_avg_diff) / len(rtt_avg_diff)
            rtt_stddev = math.sqrt(rtt_variance)
            full_summary += "round trip min/avg/max/stddev = {0}/{1}/{2}/{3} ms\n" \
                .format(rtt_min, rtt_avg, rtt_max, rtt_stddev)

        full_summary = "\n--- {0} ping statistics ---\n".format(
            dst) + full_summary
        full_summary += "{0} packets transmitted, {1} packets received, {2}% packet loss\n" \
            .format(total_sent, total_recvd, percent_lost)

        print full_summary


class Sample:

    def __init__(self, rtt, received):
        self.rtt = rtt
        self.received = received


if __name__ == '__main__':
    pinger = Pinger()

    if len(sys.argv) < 3:
        count = 0
    else:
        count = int(sys.argv[2])
    dst = sys.argv[1]

    pinger.ping_many(dst, count)
