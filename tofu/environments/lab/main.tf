terraform {
  required_version = ">= 1.8.0, < 2.0.0"
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "= 0.8.3"
    }
  }
}
provider "libvirt" { uri = "qemu:///system" }
variable "management_cidr" {
  type    = string
  default = "192.168.50.0/24"
  validation {
    condition     = can(cidrnetmask(var.management_cidr)) && can(cidrhost(var.management_cidr, 13))
    error_message = "Un CIDR IPv4 contenant au moins 16 adresses est requis."
  }
}
variable "host_count" {
  type    = number
  default = 3
  validation {
    condition     = var.host_count >= 1 && var.host_count <= 3 && floor(var.host_count) == var.host_count
    error_message = "host_count doit être un entier de 1 à 3."
  }
}
locals {
  hyperv_hosts = { for index in range(var.host_count) : format("lab-hv%02d", index + 1) => {
    ip  = cidrhost(var.management_cidr, 10 + index)
    mac = format("52:54:00:50:00:%02x", 16 + index)
  } }
}
# Preserve the first host if migrating an existing single-host state.
moved {
  from = module.windows_vm
  to   = module.windows_vm["lab-hv01"]
}
variable "vcpu" {
  type    = number
  default = 8
  validation {
    condition     = var.vcpu >= 2 && var.vcpu <= 128 && floor(var.vcpu) == var.vcpu
    error_message = "vcpu doit être un entier de 2 à 128."
  }
}
variable "memory" {
  type    = number
  default = 32768
  validation {
    condition     = var.memory >= 8192 && var.memory <= 262144 && floor(var.memory) == var.memory
    error_message = "memory doit être un entier de 8192 à 262144 Mio."
  }
}
variable "disk_size" {
  type    = number
  default = 200
  validation {
    condition     = var.disk_size >= 60 && var.disk_size <= 2048 && floor(var.disk_size) == var.disk_size
    error_message = "disk_size doit être un entier de 60 à 2048 Gio."
  }
}
variable "os_iso_path" {
  type        = string
  description = "Chemin absolu de l'ISO Windows Server fourni localement."
  validation {
    condition     = startswith(var.os_iso_path, "/") && fileexists(var.os_iso_path)
    error_message = "L'ISO Windows doit exister à un chemin absolu."
  }
}
variable "firmware_path" {
  type    = string
  default = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
  validation {
    condition     = fileexists(var.firmware_path)
    error_message = "Le firmware UEFI doit exister sur cet hôte."
  }
}
variable "seed_iso_path" {
  type        = string
  default     = ""
  description = "ISO optionnel de réponse/pilotes, préparé localement et non versionné."
  validation {
    condition     = var.seed_iso_path == "" || (startswith(var.seed_iso_path, "/") && try(fileexists(var.seed_iso_path), false))
    error_message = "L'ISO de réponse doit exister à un chemin absolu."
  }
}
variable "host_seed_iso_paths" {
  type        = map(string)
  default     = {}
  description = "Médias unattended propres à chaque hôte, générés par windows:prepare."
  validation {
    condition     = alltrue([for path in values(var.host_seed_iso_paths) : startswith(path, "/") && try(fileexists(path), false)])
    error_message = "Chaque ISO unattended doit exister à un chemin absolu."
  }
}
module "lab_network" {
  source       = "../../modules/lab-network"
  network_name = "lab-management"
  cidr         = var.management_cidr
}
module "windows_vm" {
  source         = "../../modules/windows-vm"
  for_each       = local.hyperv_hosts
  name           = each.key
  management_mac = each.value.mac
  vcpu           = var.vcpu
  memory         = var.memory
  disk_size      = var.disk_size
  management_ip  = each.value.ip
  network_id     = module.lab_network.network_id
  os_iso_path    = var.os_iso_path
  firmware_path  = var.firmware_path
  seed_iso_path  = lookup(var.host_seed_iso_paths, each.key, var.seed_iso_path)
}
output "ansible_hosts" {
  value = { for name, host in module.windows_vm : name => { ansible_host = host.management_ip } }
}
output "management_cidr" { value = var.management_cidr }
