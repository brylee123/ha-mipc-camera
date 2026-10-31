# Keep camera traffic local

[Back to the README](../README.md)

For better privacy, block the camera's internet access at your router or firewall
while allowing Home Assistant to reach it locally. Using this integration does
not stop the camera firmware from contacting vendor services on its own. Network
restrictions reduce that exposure; they do not make the camera firmware trusted.

1. Reserve the camera's LAN address in your router's DHCP settings.
2. Create an **internet-only block** for the camera: deny outbound traffic to the
   internet (WAN), across all protocols and ports, for **both IPv4 and IPv6** if
   enabled. Blocking DNS or a list of vendor domains alone is insufficient.
3. Allow Home Assistant to reach the camera's local control and media services,
   including return traffic. If using a separate camera/IoT network, add the
   required firewall rules between that network and Home Assistant. Guest-network
   isolation or a router's generic **Block device** option may also block local
   access; check what the option actually does.
4. Cover every connected camera interface. Ethernet and Wi-Fi can be active at
   the same time with different addresses; restrict both or disconnect the unused
   interface. Do not forward camera ports from the internet, and remove any
   existing camera port forwards or UPnP mappings.
5. Verify that the router enforces the WAN block, then restart the camera and
   check snapshots, live video, PTZ, settings and motion events where supported.

MIPC cloud viewing, cloud notifications, vendor updates and internet time
synchronization may stop working. If the camera needs time synchronization, use
a trusted local time server where the firmware supports it and allow only the
necessary local access. A correct camera clock matters for motion-event filtering.
Home Assistant can retain its own internet access for installation and updates;
the restriction targets the camera.

Local control and streaming have been tested, but operation with the camera's WAN
access blocked has **not yet been hardware-validated**. Verify your model after
applying the rule. The camera uses HTTP and legacy authentication on the LAN;
keep access limited to trusted devices, ideally on a separate camera/IoT network.
