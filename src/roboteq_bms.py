#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2015, Robotnik Automation SLL
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Robotnik Automation SSL nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import sys

from pyparsing import line

import rospy

import time, threading

from rcomponent import RComponent, DEFAULT_FREQ # esto podria estar como limites

import robotnik_msgs.msg

import std_msgs.msg

import serial

from serial import SerialException

class roboteq_bmsComponent(RComponent):
	def __init__(self):
		RComponent.__init__(self)

		self.port = rospy.get_param('~port', '/dev/ttyACM0')
		self.baud = rospy.get_param('~baud', 115200)
		self.read_errors = 0
		self.bat_level= 0.0
		self.voltage = 0.0
		self.current = 0.0
		self.cell_voltages = ''
		self.cell_currents = ''
		self.status_flags = ''
		self.fault_flags = ''
		self.battery_status_message = robotnik_msgs.msg.BatteryStatus()
		self.bms_temperature = robotnik_msgs.msg.BMS_Temperature()
		self.status_flags_msg = std_msgs.msg.String()
		self.fault_flags_msg = std_msgs.msg.String()
		self.serial_device = None
		
	def setup(self):

		RComponent.setup(self)
		self.serial_device = serial.Serial(
			port= self.port,
			baudrate=self.baud,
			parity=serial.PARITY_NONE,
			stopbits=1,
			bytesize=8,
			timeout=0.1,
			xonxoff=False,
			dsrdtr=False,
		rtscts=False
		)



	def shutdown(self):
		RComponent.shutdown(self)

		rospy.loginfo("roboteq_bms::shutdown")

		if self.serial_device != None and not self.serial_device.closed:
			self.serial_device.close()

		return 0

	def rosSetup(self):
		RComponent.rosSetup(self)

		self.bat_data_publisher_ = rospy.Publisher('~data', robotnik_msgs.msg.BatteryStatus, queue_size=100)
		self.bms_temp_publisher_ = rospy.Publisher('~temperature', robotnik_msgs.msg.BMS_Temperature, queue_size=100)
		self.status_flags_publisher_ = rospy.Publisher('~status_flags', std_msgs.msg.String, queue_size=100)
		self.fault_flags_publisher_ = rospy.Publisher('~fault_flags', std_msgs.msg.String, queue_size=100)

	def rosShutdown(self):
		if self._running:
			rospy.logwarn("%s::rosShutdown: cannot shutdown because the component is still running" % self.node_name)
			return -1
		elif not self._ros_initialized:
			rospy.logwarn("%s::rosShutdown: cannot shutdown because the component was not setup" % self.node_name)
			return -1

		RComponent.rosShutdown(self)

		self.bat_data_publisher_.unregister()
		self.bms_temp_publisher_.unregister()
		self.status_flags_publisher_.unregister()
		self.fault_flags_publisher_.unregister()

	def readyState(self):
		if not rospy.is_shutdown():

			emptys = []
			self.writeToSerialDevice("?BSC" + "\r")
			line_read = str(self.readFromSerialDevice())

			try:
				if line_read != '':
					self.bat_level = float(line_read.partition("BSC=")[2])
					self.battery_status_message.level = self.bat_level
					emptys.append(False)
				else:
					emptys.append(True)
			except ValueError as e:
				#rospy.logerr('%s::readyState: error reading ?BSC - response (%s): %s', rospy.get_name(), line_read, e)
				emptys.append(True)

			self.writeToSerialDevice("?A 1" + "\r")
			line_read = str(self.readFromSerialDevice())


			try:
				if line_read != '':
					self.current = float(line_read.partition("A=")[2])
					self.battery_status_message.current = self.current*0.01
					if self.battery_status_message.current > 0.0:
						self.battery_status_message.is_charging = True
					else:
						self.battery_status_message.is_charging = False
					emptys.append(False)
				else:
					emptys.append(True)
			except ValueError as e:
				#rospy.logerr('%s::readyState: error reading ?A 1 - response (%s):: %s', rospy.get_name(), line_read, e)
				emptys.append(True)

			self.writeToSerialDevice("?V 1" + "\r")
			line_read = str(self.readFromSerialDevice())

			try:
				if line_read != '':
					self.voltage = float(line_read.partition("V=")[2])
					self.battery_status_message.voltage = self.voltage*0.01
					emptys.append(False)
				else:
					emptys.append(True)
			except ValueError as e:
				#rospy.logerr('%s::readyState: error reading ?V 1 - response (%s):: %s', rospy.get_name(), line_read, e)
				emptys.append(True)


			self.writeToSerialDevice("?V" + "\r")
			line_read = str(self.readFromSerialDevice())
			
			try:
				if line_read != '':
					voltage = (line_read.partition("V="))
					voltage = voltage[2].split(":")
					cell_voltages = list(map(float, voltage[3:11]))
					cell_voltages = [val * 0.001 for val in cell_voltages]
					self.battery_status_message.min_cell = min(cell_voltages)
					self.battery_status_message.max_cell = max(cell_voltages)
					self.battery_status_message.avg_cell = sum(cell_voltages)/len(cell_voltages)
					emptys.append(False)
				else:
					emptys.append(True)
			except ValueError as e:
				#rospy.logerr('%s::readyState: error reading ?V 1 - response (%s):: %s', rospy.get_name(), line_read, e)
				emptys.append(True)


			self.writeToSerialDevice("?T" + "\r")
			line_read = str(self.readFromSerialDevice())

			try:
				if line_read != '':
					temperature = line_read.partition("T=")[2]
					temperature = temperature.split(":")
					self.temperature = list(map(int, temperature))
					self.bms_temperature.data = self.temperature[:3]
					emptys.append(False)
				else:
					emptys.append(True)
			except ValueError as e:
				#rospy.logerr('%s::readyState: error reading ?T - response (%s):: %s', rospy.get_name(), line_read, e)
				emptys.append(True)



			self.writeToSerialDevice("?FS" + "\r")
			line_read = str(self.readFromSerialDevice())


			try:
				if line_read != '':
					self.status_flags = line_read.partition("FS=")[2]
					self.status_flags_msg.data = self.status_flags.replace("\r", "")
					emptys.append(False)
				else:
					emptys.append(True)
			except ValueError as e:
				#rospy.logerr('%s::readyState: error reading ?FS - response(%s): %s', rospy.get_name(), line_read, e)
				emptys.append(True)



			self.writeToSerialDevice("?FF" + "\r")
			line_read = str(self.readFromSerialDevice())

			try:
				if line_read != '':
					self.fault_flags = line_read.partition("FF=")[2]
					self.fault_flags_msg.data = self.fault_flags.replace("\r", "")
					emptys.append(False)
				else:
					emptys.append(True)
			except ValueError as e:
				#rospy.logerr('%s::readyState: error reading ?FF - response(%s): %s', rospy.get_name(), line_read, e)
				emptys.append(True)


			if all(emptys):
				rospy.logerr('%s::readyState: no response from bms', self._node_name)
				self.switchToState(robotnik_msgs.msg.State.FAILURE_STATE)
			elif any(emptys):
				#rospy.logwarn_once('%s::readyState: some response msgs from bms are empty', self._node_name)
				pass


	def rosPublish(self):
		RComponent.rosPublish(self)
		self.bat_data_publisher_.publish(self.battery_status_message)
		self.bms_temp_publisher_.publish(self.bms_temperature)
		self.status_flags_publisher_.publish(self.status_flags_msg)
		self.fault_flags_publisher_.publish(self.fault_flags_msg)

	def writeToSerialDevice(self, data):
		bytes_written = self.serial_device.write(data)
		return bytes_written

	def readFromSerialDevice(self):
		try:
			data_read = self.serial_device.readline().replace('\x00', '')

		except SerialException as e:
			#rospy.logwarn(e)
			return

		return data_read

def main():
    rospy.init_node("roboteq_bms")

    _name = rospy.get_name().replace('/','')

    roboteq_bms_node = roboteq_bmsComponent()

    roboteq_bms_node.start()

if __name__ == "__main__":
	main()
