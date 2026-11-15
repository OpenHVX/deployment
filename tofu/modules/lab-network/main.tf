terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "= 0.8.3"
    }
  }
}
variable "network_name" { type = string }
variable "cidr" { type = string }
resource "libvirt_network" "lab_net" {
  name      = var.network_name
  mode      = "nat"
  addresses = [var.cidr]
  autostart = true
  dhcp { enabled = true }
  dns { enabled = true }
}
output "network_id" { value = libvirt_network.lab_net.id }
