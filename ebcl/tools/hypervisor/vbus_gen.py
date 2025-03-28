from pathlib import Path
import re
import yaml
import logging
import os

class DTSConverter:
    def __init__(self, dts: Path):
        self.dts_file_path = dts
        self.current_node : dict | None = None
        self.nodes : list = []
        
        self.node_hierarchy : list = []  # Stack to track parent nodes
        self.yaml_output = self.process_dts_file(self.dts_file_path)

    def parse_compatible_property(self, compatible_property) -> str:
        """Parse the compatible property and return as a list of strings."""
        compatible_values = compatible_property.strip('";')
        return compatible_values

    def parse_reg_property(self, reg_property, size_cell: int, address_cell: int) -> list:
        """Parse the reg property and return a list of dictionaries with base address and size."""
        reg_values = reg_property.replace('<', '').replace('>', '').replace(';', '').split()
        mmios: list = []

        if len(reg_values) < (size_cell + address_cell):
            return mmios  # Not enough values to parse

        print(f"Reg values: {reg_values}, Address Cells: {address_cell}, Size Cells: {size_cell}")

        for i in range(0, len(reg_values), size_cell + address_cell):
            if i + address_cell + size_cell > len(reg_values):
                logging.warning(f"Incomplete reg entry: {reg_values[i:]}")
                break  # Prevent index errors

            base_address = 0
            size = 0

            # Extract address (1 or 2 cells)
            if address_cell == 1:
                base_address = int(reg_values[i], 16)
            elif address_cell == 2:
                base_address = (int(reg_values[i], 16) << 32) + int(reg_values[i + 1], 16)

            # Extract size (1 or 2 cells)
            if size_cell == 1:
                size = int(reg_values[i + address_cell], 16)
            elif size_cell == 2:
                size = (int(reg_values[i + address_cell], 16) << 32) + int(reg_values[i + address_cell + 1], 16)

            mmios.append({"address": f"0x{base_address:x}", "size": f"0x{size:x}"})

        return mmios

    def parse_interrupts_property(self, interrupts_property) -> list:
        """Parse the interrupts property and return a list of dictionaries with IRQ numbers."""
        interrupts_cleaned = interrupts_property.replace('<', '').replace('>', '').replace(';', '').split()
        irqs: list = []
        
        if len(interrupts_cleaned) == 1:
            logging.warning(f'TODO: Only one interrupt entry: {interrupts_cleaned[0]}')
            return irqs

        for i in range(0, len(interrupts_cleaned), 3):
            interrupt_id = int(interrupts_cleaned[i + 1], 16)  # Second value in the group is the interrupt ID
            irq_number = 32 + interrupt_id  # Convert interrupt ID to IRQ number
            irqs.append({"irq": irq_number, "trigger": "level_high"})

        return irqs
    
    def parse_cells_info(self, cell_property) -> int:
        cell_cleaned = cell_property.replace('<', '').replace('>','').replace(';','')
        cell = int(cell_cleaned, 16)
        return cell
    
    def parse_node_full_name(self, node_match: re.Match[str]) -> str:
        node_name, unit_address = node_match.groups()
        full_name = node_name if not unit_address else f"{node_name}@{unit_address}"
        return full_name
    

    def process_dts_file(self, dts_file_path):
        """Parse a DTS file and convert it into the YAML structure."""
        try:
            with open(dts_file_path, 'r') as dts_file:
                dts_lines = dts_file.readlines()
            
            # Regex patterns to extract nodes and properties
            node_pattern = re.compile(r'([a-zA-Z0-9\-_]+)\s*@?([\da-fA-Fx]*)\s*{')
            compatible_pattern = re.compile(r'compatible\s*=\s*(\"[^\"]+\")\s*;')
            reg_pattern = re.compile(r'reg\s*=\s*(<[^>]+>)')
            interrupts_pattern = re.compile(r'interrupts\s*=\s*(<[^>]+>)')
            status_pattern = re.compile(r'status\s*=\s*(\"?[a-zA-Z0-9_]+\"?)\s*;')
            size_cell_pattern = re.compile(r'#size-cells\s*=\s*<\s*(0x[0-9a-fA-F]+)\s*>')
            address_cell_pattern = re.compile(r'#address-cells\s*=\s*<\s*(0x[0-9a-fA-F]+)\s*>')
            end_node_pattern = re.compile(r'}')  # Matches closing brace of a node

            devices: list = []
            size_cells: dict = {}
            address_cells: dict = {}
            current_node: dict = {}
            
            for line in dts_lines:
                line = line.strip()
                # Detect new node
                node_match = node_pattern.match(line)
                if node_match:
                    full_name = self.parse_node_full_name(node_match)

                    # Track current node and its parent
                    parent = self.node_hierarchy[-1] if self.node_hierarchy else None
                    current_node = {
                        "name": full_name,
                        "depth": len(self.node_hierarchy),
                        "parent": parent,
                        "size-cells": size_cells.get(len(self.node_hierarchy), 1),  # Default to 1
                        "address-cells": address_cells.get(len(self.node_hierarchy), 1),  # Default to 1
                    }
                    self.nodes.append(current_node)
                    self.node_hierarchy.append(full_name)  # Push to stack
                    continue

                # Detect end of a node
                if end_node_pattern.match(line):
                    if self.node_hierarchy:
                        self.node_hierarchy.pop()  # Pop from stack when node closes
                    continue
                
                size_match = size_cell_pattern.match(line)
                if size_match:
                    size_cells[len(self.node_hierarchy)] = self.parse_cells_info(size_match.group(1))
                    logging.debug(f"Set size-cells[{len(self.node_hierarchy)}] = {size_cells[len(self.node_hierarchy)]}")
                    continue

                address_match = address_cell_pattern.match(line)
                if address_match:
                    address_cells[len(self.node_hierarchy)] = self.parse_cells_info(address_match.group(1))
                    logging.debug(f"Set address-cells[{len(self.node_hierarchy)}] = {address_cells[len(self.node_hierarchy)]}")
                    continue
                
                reg_match = reg_pattern.match(line)
                if reg_match:
                    if 'reg' not in current_node:
                        current_node['reg'] = []  # Ensure 'reg' exists
                    current_node['reg'].extend(self.parse_reg_property(reg_match.group(1), 
                                                                    current_node['size-cells'], 
                                                                    current_node['address-cells']))
                    continue
                
                compatible_match = compatible_pattern.match(line)
                if compatible_match and current_node:
                    current_node['compatible'] = self.parse_compatible_property(compatible_match.group(1))
                    continue
                
                interrupts_match = interrupts_pattern.match(line)
                if interrupts_match:
                    current_node['irq'] = self.parse_interrupts_property(interrupts_match.group(1))
                    continue
                
                status_match = status_pattern.match(line)
                if status_match:
                    current_node['status'] = "disabled" if "disabled" in status_match.group(1) else "okay"
            
            for mynode in self.nodes:
                if not all(key in mynode for key in ["compatible", "reg"]):
                    continue
                
                if "status" in mynode and mynode["status"] == "disabled":
                    continue

                device_entry = {
                    "name": mynode["name"],
                    "compatible": mynode["compatible"],
                    "mmios": mynode["reg"],
                    "irqs": mynode["irq"] if "irq" in mynode else None
                }
                devices.append(device_entry)

            # Construct final YAML structure
            yaml_output = {
                "vbus": [
                    {
                        "name": "vm_hw",
                        "devices": devices
                    }
                ]
            }

            return yaml.dump(yaml_output, default_flow_style=False, sort_keys=False, default_style=None)

        except FileNotFoundError:
            logging.error(f"Error: The file {dts_file_path} was not found.")
    
    def dump(self):
        path = os.path.join(os.path.dirname(self.dts_file_path), "test.yaml")
        mode: str = 'x'
        if os.path.exists(path):
            mode = 'w'
        with open(path, mode) as file:
            file.write(self.yaml_output)
