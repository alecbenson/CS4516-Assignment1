import socket
from struct import *
import random
import array
import select
import time
import sys
import math
from operator import attrgetter


class Pinger:

    def __init__(self):
        self.samples = SampleList()

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
            self.samples.add(elapsed, True)
        else:
            self.samples.add(1, False)
            print "Request timed out"

    def traceroute(self, dst):
        dst_ip = self.gethostname(dst);
        for i in range(10):
            s = self.make_socket()
            s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, pack('I', i))
            p_id = random.randint(0, 65535)

            packet = self.icmp(p_id, i)
            sent = s.sendto(packet, (dst_ip, 1))
            self.recv_tracert(s, p_id, time.time(), dst)

    def recv_tracert(self, s, p_id, start_time, dst):
        # Wait until data is available or timeout occurs
        ready = select.select([s], [], [], 1)
        if ready[0]:
            recv_packet, addr = s.recvfrom(1024)

            elapsed = 1000 * (time.time() - start_time)
            ip = unpack('!BBHHHBBH4s4s', recv_packet[:20])
            icmp = unpack('bbHHh', recv_packet[20:28])
            hopNum = ip[5]

            print "{0}\t{1}".format(hopNum, addr[0])
        else:
            print "Request timed out"

    def make_socket(self):
        # Create the socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                              socket.IPPROTO_ICMP)
        except socket.error as e:
            print e
            sys.exit()
        return s

    def gethostname(self, dst):
        try:
            dst_ip = socket.gethostbyname(dst)
        except socket.gaierror as e:
            print e
            return
        return dst_ip

    def ping(self, dst, seq=0):
        # Convert the url to an IP
        dst_ip = self.gethostname(dst)
        s = self.make_socket()
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
            self.samples.print_summary(dst)
            sys.exit()
        self.samples.print_summary(dst)


class Sample:

    def __init__(self, rtt, received):
        self.rtt = rtt
        self.received = received


class SampleList:

    def __init__(self, samples=[]):
        self.samples = samples

    def total(self):
        return len(self.samples)

    def total_recvd(self):
        received = self.received()
        return len(received)

    def min(self):
        received = self.received()
        least = min(received, key=attrgetter('rtt'))
        return least.rtt

    def max(self):
        received = self.received()
        most = max(received, key=attrgetter('rtt'))
        return most.rtt

    def received(self):
        return [s for s in self.samples if s.received == True]

    def avg(self):
        received = self.received()
        sum_rtt = self.sum_rtt()
        return sum_rtt / len(received)

    def sum_rtt(self):
        return sum(s.rtt for s in self.samples if s.received == True)

    def variance(self):
        avg = self.avg()
        received = self.received()
        avg_diff = map(lambda x: (x.rtt - avg)**2, received)
        return sum(avg_diff) / len(avg_diff)

    def std_dev(self):
        variance = self.variance()
        return math.sqrt(variance)

    def percent_lost(self):
        received = self.received()
        total = float(self.total())
        return (1 - (len(received) / total)) * 100

    def num_lost(self):
        received = self.received()
        return self.total() - len(received)

    def add(self, rtt, received):
        sample = Sample(rtt, received)
        self.samples.append(sample)

    def print_summary(self, dst):
        full_summary = ""

        total_packets = self.total()
        total_recvd = self.total_recvd()
        num_lost = self.num_lost()
        percent_lost = self.percent_lost()

        if(total_recvd > 0):
            rtt_min = self.min()
            rtt_max = self.max()
            rtt_avg = self.avg()
            rtt_stddev = self.std_dev()

            full_summary += "round trip min/avg/max/stddev = {0}/{1}/{2}/{3} ms\n" \
                .format(rtt_min, rtt_avg, rtt_max, rtt_stddev)

        full_summary = "\n--- {0} ping statistics ---\n".format(
            dst) + full_summary
        full_summary += "{0} packets transmitted, {1} packets received, {2}% packet loss\n" \
            .format(total_packets, total_recvd, percent_lost)

        print full_summary


if __name__ == '__main__':
    pinger = Pinger()

    if len(sys.argv) < 3:
        count = 0
    else:
        count = int(sys.argv[2])
    dst = sys.argv[1]

    pinger.traceroute(dst)
