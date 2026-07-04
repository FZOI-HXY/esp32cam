#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32-CAM 蓝牙控制程序
用于通过电脑蓝牙控制ESP32-CAM拍照
"""

import bluetooth
import time
import sys

class BluetoothController:
    def __init__(self):
        self.server_socket = None
        self.client_socket = None
        self.port = 1
    
    def start_server(self):
        """启动蓝牙服务器"""
        try:
            self.server_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.server_socket.bind(('', self.port))
            self.server_socket.listen(1)
            
            print("等待蓝牙连接...")
            print(f"蓝牙服务器运行在端口 {self.port}")
            print("请在ESP32-CAM端搜索并连接此设备")
            
            self.client_socket, address = self.server_socket.accept()
            print(f"连接成功！地址: {address}")
            
            return True
        except Exception as e:
            print(f"启动蓝牙服务器失败: {e}")
            return False
    
    def send_command(self, command):
        """发送命令到ESP32-CAM"""
        if not self.client_socket:
            print("未连接到设备")
            return False
        
        try:
            self.client_socket.send(command)
            print(f"发送命令: {command}")
            return True
        except Exception as e:
            print(f"发送命令失败: {e}")
            return False
    
    def receive_data(self):
        """接收ESP32-CAM的响应"""
        if not self.client_socket:
            print("未连接到设备")
            return None
        
        try:
            data = self.client_socket.recv(1024)
            print(f"收到响应: {data.decode('utf-8')}")
            return data
        except Exception as e:
            print(f"接收数据失败: {e}")
            return None
    
    def close(self):
        """关闭蓝牙连接"""
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        print("蓝牙连接已关闭")

def main():
    print("ESP32-CAM 蓝牙控制程序")
    print("=" * 50)
    
    controller = BluetoothController()
    
    if not controller.start_server():
        print("无法启动蓝牙服务器，退出程序")
        return
    
    try:
        while True:
            print("\n命令选项:")
            print("1. 发送拍照指令 (capture)")
            print("2. 发送测试指令 (test)")
            print("3. 退出程序 (exit)")
            
            choice = input("请输入命令编号: ")
            
            if choice == '1':
                controller.send_command('capture')
            elif choice == '2':
                controller.send_command('test')
            elif choice == '3':
                print("退出程序...")
                break
            else:
                print("无效命令，请重新输入")
                
    except KeyboardInterrupt:
        print("\n用户中断程序")
    finally:
        controller.close()

if __name__ == "__main__":
    main()
