terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "= 0.8.3"
    }
  }
}

variable "name" {
  type = string
}

variable "vcpu" {
  type = number
}

variable "memory" {
  type = number
}

variable "disk_size" {
  type = number
}

variable "management_ip" {
  type = string
}

variable "management_mac" { type = string }

variable "network_id" {
  type = string
}

variable "os_iso_path" {
  type = string
}


variable "firmware_path" { type = string }
variable "seed_iso_path" { type = string }
resource "libvirt_pool" "windows_pool" {
  name = "${var.name}-images"
  type = "dir"
  target {
    path = "/var/lib/libvirt/images/${var.name}"
  }
}
resource "libvirt_volume" "windows_disk" {
  name   = "${var.name}.qcow2"
  pool   = libvirt_pool.windows_pool.name
  format = "qcow2"
  size   = var.disk_size * 1024 * 1024 * 1024
}
resource "libvirt_domain" "windows_vm" {
  name    = var.name
  memory  = var.memory
  vcpu    = var.vcpu
  type    = "kvm"
  machine = "q35"
  xml { xslt = file("${path.module}/windows-domain.xsl") }
  firmware  = var.firmware_path
  autostart = true
  cpu { mode = "host-passthrough" }
  boot_device { dev = ["hd", "cdrom"] }
  disk { volume_id = libvirt_volume.windows_disk.id }
  disk { file = var.os_iso_path }
  dynamic "disk" {
    for_each = var.seed_iso_path == "" ? [] : [var.seed_iso_path]
    content { file = disk.value }
  }
  network_interface {
    network_id = var.network_id
    hostname   = var.name
    addresses  = [var.management_ip]
    mac        = var.management_mac
  }
  graphics {
    type           = "spice"
    listen_type    = "address"
    listen_address = "127.0.0.1"
    autoport       = true
  }
}
output "name" { value = libvirt_domain.windows_vm.name }
output "management_ip" { value = var.management_ip }
