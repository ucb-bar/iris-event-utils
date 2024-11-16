import pandas as pd
import numpy as np
import json
import networkx as nx
import time
import heapq
import subprocess
from subprocess import Popen, PIPE, STDOUT
from sys import platform
import argparse
import time
import itertools 

CLI=argparse.ArgumentParser()
CLI.add_argument(
    "--log_file",
    type=str,
    required=True,
    help="input json list file generated by VCS/Verilator with GenEvent annotations"
)
CLI.add_argument(
    "--schema_file",
    type=str,
    required=True,
    help="json input file specifying pipeline stages and associated data types"
)
CLI.add_argument(
    "--output_file",
    type=str,
    default="konnata_output.log",
    help="output file in Konata log format for visualization"
)
CLI.add_argument(
    "--verbose",
    action='store_true',
    default=False,
    help='Verbose setting on size of Konata log'
)
CLI.add_argument(
    "--gemmini",
    action='store_true',
    default=False,
    help='Boolean argument for Gemmini instruction decoding'
)

args = CLI.parse_args()

#------- Gemmini instruction decode --------
#Gemmini Instructions: https://github.com/ucb-bar/gemmini-rocc-tests/blob/13e7e1fce1a8d332eea563c14130136ef0533b16/include/gemmini.h
#RoCC format: https://inst.eecs.berkeley.edu/~cs250/sp17/disc/lab2-disc.pdf
stationary_type = {
    0: "OUTPUT_STATIONARY",
    1: "WEIGHT_STATIONARY"
}

activation_type = {
    0: "NO_ACTIVATION",
    1: "RELU",
    2: "LAYERNORM",
    3: "IGELU",
    4: "SOFTMAX"
}

config_type = {
    0: "CONFIG_EX",
    1: "CONFIG_LD",
    2: "CONFIG_ST",
    3: "CONFIG_BERT"
}

masks = { # masks for extracting bits from rs1
    "first_16_bits": 0xFFFF,
    "first_32_bits": 0xFFFFFFFF,
    "3rd_bit": 0x4,
    "4th_bit": 0x8,
    "9th_bit": 0x100,
    "10th_bit": 0x200,
    "16_32_bits": 0xFFFF0000,
    "32_48_bits": 0xFFFF00000000,
    "32_64_bits": 0xFFFF000000000000,
}

def decode_default(rs1, rs2):
    return f"rs1: {hex(rs1)}, rs2: {hex(rs2)}"

def decode_config(rs1, rs2):
    last_2_bits = rs1 & 0x3 # last 2 bits of rs1 
    config = config_type[last_2_bits]
    if last_2_bits == 0: # CONFIG_EX
        config += f"  Output stationary: {stationary_type[(rs1 & masks['3rd_bit']) >> 2]}, Activation: {activation_type[(rs1 & masks['4th_bit']) >> 3]}"
        stride = rs1 & masks["16_32_bits"] >> 16
        scalar = rs1 & masks["32_64_bits"] >> 32
        right_shift = rs2 & 0xFF
        config += f", stride: {hex(stride)}, scalar: {hex(scalar)}, right shift: {hex(right_shift)}"
    elif last_2_bits == 1: # CONFIG_LD
        spad_stride = rs1 & masks["16_32_bits"] >> 16
        scale = rs1 & masks["32_64_bits"] >> 32
        mem_stride = rs2 & 0xFFFF
        config += f"  Spad stride: {hex(spad_stride)}, scale: {hex(scale)}, mem stride: {hex(mem_stride)}"
    elif last_2_bits == 2: # CONFIG_ST
        stride = rs2 & 0xFFFF
    return config
        
def decode_mvin(rs1, rs2):
    dram_addr = hex(rs1)
    local_addr = rs2 & 0xFFFFFFFF
    num_col = rs2 & 0xFFFF00000000 >> 32
    num_rows = rs2 & 0xFFFF000000000000 >> 48
    return f"DRAM addr: {dram_addr}, Scratchpad addr: {hex(local_addr)}, {num_col} cols loaded, {num_rows} rows loaded"

def decode_mvout(rs1, rs2):
    dram_addr = hex(rs1)
    local_addr = rs2 & 0xFFFFFFFF
    num_col = rs2 & 0xFFFF00000000 >> 32
    num_rows = rs2 & 0xFFFF000000000000 >> 48
    return f"DRAM addr: {dram_addr}, Scratchpad addr: {hex(local_addr)}, {num_col} cols loaded, {num_rows} rows loaded"

def decode_compute(rs1, rs2):
    a_local_addr = rs1 & 0xFFFFFFFF
    a_col = rs1 & 0xFFFF00000000 >> 32
    a_row = rs1 & 0xFFFF000000000000 >> 48
    b_local_addr = rs2 & 0xFFFFFFFF
    b_col = rs2 & 0xFFFF00000000 >> 32
    b_row = rs2 & 0xFFFF000000000000 >> 48
    return f"A Scratchpad addr: {hex(a_local_addr)}, {a_col} cols, {a_row} rows, D/B Scratchpad addr: {hex(b_local_addr)}, {b_col} cols, {b_row} rows"

def decode_preload(rs1, rs2):
    d_local_addr = rs1 & 0xFFFFFFFF
    d_col = rs1 & 0xFFFF00000000 >> 32
    d_row = rs1 & 0xFFFF000000000000 >> 48
    c_local_addr = rs2 & 0xFFFFFFFF
    c_col = rs2 & 0xFFFF0000 >> 32
    c_row = rs2 & 0xFFFF000000000000 >> 48
    return f"D/B Scratchpad addr: {hex(d_local_addr)}, {d_col} cols, {d_row} rows, C Scratchpad addr: {hex(c_local_addr)}, {c_col} cols, {c_row} rows"

def decode_config_bounds(rs1, rs2):
    """
    RS1: The padding for I is in the lowest 16 bits, 
    J in the next 16 bits, and K in the highest 32 bits of rs1.
    RS2: The actual addresses is in the same order
    """
    i_pad = rs1 & masks["first_16_bits"]
    j_pad = rs1 & masks["16_32_bits"] >> 16
    k_pad = rs1 & masks["32_64_bits"] >> 32
    i_addr = rs2 & masks["first_16_bits"]
    j_addr = rs2 & masks["16_32_bits"] >> 16
    k_addr = rs2 & masks["32_64_bits"] >> 32
    return f"Padding: I: {hex(i_pad)}, J: {hex(j_pad)}, K: {hex(k_pad)}, Addresses: I: {hex(i_addr)}, J: {hex(j_addr)}, K: {hex(k_addr)}"

def decode_loop_ws(rs1, rs2):
    """
    rs1: Encodes various flags:
    act: Activation function, shifted left by 8 bits.
    low_D: A flag, shifted left by 2 bits.
    full_C: A flag, shifted left by 1 bit.
    ex_accumulate: A flag to determine the accumulation behavior.
    rs2: Contains flags for matrix transpositions:
    B_transpose: Indicates if matrix B is transposed, shifted left by 1.
    A_transpose: Indicates if matrix A is transposed.
    """
    act = rs1 & 0xFF
    low_D = rs1 & 0x4
    full_C = rs1 & 0x2
    ex_accumulate = rs1 & 0x1
    B_transpose = rs2 & 0x2
    A_transpose = rs2 & 0x1
    return f"Activation: {activation_type[act]}, Low D: {low_D}, Full C: {full_C}, Ex Accumulate: {ex_accumulate}, B Transpose: {B_transpose}, A Transpose: {A_transpose}"

def decode_loop_conv_ws(rs1, rs2, config):
    rs1_map_config = {
        0: ("RS1"), # all 64 bits
        1: ("Output Channels", "Input Channels", "IN DIM", "BATCH SIZE"), # 16 bits per, from 64 to 0
        2: ("Kernel DIM", "Pool Size", "Stride", "Pad"), # 16 bits per, from 64 to 0
        3: ("K Rows", "K Cols", "K Chs", "L PAD"), # 16 bits per, from 64 to 0
        4: ("O Rows", "O Cols", "P UPAD", "P DPAD"), # 16 bits per, from 64 to 0
        5: ("Weights"), # 64 bits
        6: ("Bias"), # 64 bits
    }
    rs2_map_config = {
        0: ("RS2"), # all 64 bits
        1: ("Padding", "Stride", "Pool Out DIM", "Out DIM"), # 16 bits per, from 64 to 0
        2: ("Batches", "P Rows", "P Cols", "P Chs"), # 16 bits per, from 64 to 0
        3: ("R Pad", "U Pad", "D Pad", "PL Pad"), # 16 bits per, from 64 to 0
        4: ("Kernel Dialation", "O Cols"), # 16 bits per, from 32 to 0
        5: ("Output"), # 64 bits
        6: ("Input"), # 64 bits
    }
    rs1_config = rs1_map_config[config]
    rs2_config = rs2_map_config[config]
    rs1_str = ""
    rs2_str = ""
    for i in range(len(rs1_config)):
        if len(rs1_config) == 1:
            rs1_str += f"{rs1_config[i]}: {hex(rs1)}, "
        elif len(rs1_config) == 4:
            rs1_str += f"{rs1_config[i]}: {hex(rs1 & masks['first_16_bits'])}, "
            rs1 >>= 16
        elif len(rs1_config) == 2:
            rs1_str += f"{rs1_config[i]}: {hex(rs1 & masks['first_32_bits'])}, "
            rs1 >>= 32
        else:
            rs1_str += f"{rs1_config[i]}: {hex(rs1)}, "
    for i in range(len(rs2_config)):
        if len(rs2_config) == 1:
            rs2_str += f"{rs2_config[i]}: {hex(rs2)}, "
        elif len(rs2_config) == 4:
            rs2_str += f"{rs2_config[i]}: {hex(rs2 & masks['first_16_bits'])}, "
            rs2 >>= 16
        elif len(rs2_config) == 2:
            rs2_str += f"{rs2_config[i]}: {hex(rs2 & masks['first_32_bits'])}, "
            rs2 >>= 32
        else:
            rs2_str += f"{rs2_config[i]}: {hex(rs2)}, "
    return rs1_str + rs2_str

def gemmini_decode(cmd: int):
    gemmini_funct = {
        0: "k_CONFIG",
        1: "k_MVIN2",
        2: "k_MVIN",
        3: "k_MVOUT",
        4: "k_COMPUTE_PRELOADED",
        5: "k_COMPUTE_ACCUMULATE",
        6: "k_PRELOAD",
        7: "k_FLUSH",
        8: "k_LOOP_WS",
        9: "k_LOOP_WS_CONFIG_BOUNDS",
        10: "k_LOOP_WS_CONFIG_ADDRS_AB",
        11: "k_LOOP_WS_CONFIG_ADDRS_DC",
        12: "k_LOOP_WS_CONFIG_STRIDES_AB",
        13: "k_LOOP_WS_CONFIG_STRIDES_DC",
        14: "k_MVIN3",
        126: "k_COUNTER",
        15: "k_LOOP_CONV_WS",
        16: "k_LOOP_CONV_WS_CONFIG_1",
        17: "k_LOOP_CONV_WS_CONFIG_2",
        18: "k_LOOP_CONV_WS_CONFIG_3",
        19: "k_LOOP_CONV_WS_CONFIG_4",
        20: "k_LOOP_CONV_WS_CONFIG_5",
        21: "k_LOOP_CONV_WS_CONFIG_6"
    }

    gemmini_decode_f = {
        0: decode_config,
        1: decode_mvin,
        2: decode_mvin,
        3: decode_mvout,
        4: decode_compute,
        5: decode_compute,
        6: decode_preload,
        7: lambda rs1, rs2: "TLB Req skipped" if rs1 % 2 == 1 else "not flush TLB",
        8: decode_loop_ws,
        9: decode_config_bounds,
        10: lambda rs1, rs2: f"A addr: {hex(rs1)}, B addr: {hex(rs2)}",
        11: lambda rs1, rs2: f"D addr: {hex(rs1)}, C addr: {hex(rs2)}",
        12: lambda rs1, rs2: f"A stride: {rs1}, B stride: {rs2}",
        13: lambda rs1, rs2: f"D stride: {rs1}, C stride: {rs2}",
        14: decode_mvin,
        126: decode_default,
        15: lambda rs1, rs2: decode_loop_conv_ws(rs1, rs2, 0),
        16: lambda rs1, rs2: decode_loop_conv_ws(rs1, rs2, 1),
        17: lambda rs1, rs2: decode_loop_conv_ws(rs1, rs2, 2),
        18: lambda rs1, rs2: decode_loop_conv_ws(rs1, rs2, 3),
        19: lambda rs1, rs2: decode_loop_conv_ws(rs1, rs2, 4),
        20: lambda rs1, rs2: decode_loop_conv_ws(rs1, rs2, 5),
        21: lambda rs1, rs2: decode_loop_conv_ws(rs1, rs2, 6)
    }

    xlen = 64
    inst_mask = 0xFFFFFFFF #cmd is [rs1, rs2, inst] where inst=32bits, rs1 and rs2=64bits
    rs_mask = (1 << xlen) - 1 #FFFFFFFFFFFFFFFFF
    inst = cmd & inst_mask
    rs1_data = (cmd >> (xlen + 32)) & rs_mask
    rs2_data = (cmd >> 32) & rs_mask
    funct7_mask = 0xFE000000
    rs1_mask = 0x000F8000
    rs2_mask = 0x01F00000
    rd_mask =  0x00000F80
    # rs1 = (rs1_mask & cmd) >> 15
    # rs2 = (rs2_mask & cmd) >> 20
    # rd = (rd_mask & cmd) >> 7
    inst_funct = (funct7_mask & inst) >> 25
    if inst_funct in gemmini_funct:
        if rs1_data == 0 and rs2_data == 0:
            return gemmini_funct[inst_funct]
        else:
            decoded = gemmini_decode_f[inst_funct](rs1_data, rs2_data)
            return f"{gemmini_funct[inst_funct]} {decoded}"
    return cmd

    
# Read log JSON
with open(args.log_file, 'r') as f:
    lines = f.readlines()

inst_jsons = []
for line in lines:
    try:
        line = line.split(" ")
        if line[1] == 0:
            continue
        data = {}
        data["event_name"] = line[0]
        data["id"] = line[1]
        data["parents"] = line[2] if line[2] != "0" else "None"
        data["cycle"] = line[3]
        data["data"] = line[4]
        inst_jsons.append(data)
        # inst_jsons.append(json.loads(line))
    except json.JSONDecodeError:
        pass

# Read schema JSON
json_schema = json.load(open(args.schema_file))
event_names = json_schema["event_names"]
start_stages = json_schema["start_stages"]
split_stages = json_schema["split_stages"]
end_stages = json_schema["end_stages"]
datatypes = json_schema["event_types"]
event_to_datatype = {e:d for e, d in zip(event_names, datatypes)}

def generate_data_array(jsons):
    """
    Decodes data field of GenEvent annotations. Inputs all data into 
    Spike Disassembler and optionally decodes Gemmini instructions
    """
    dasm_input = ""
    inst_dump_list = []
    for json in jsons:
        if args.gemmini and event_to_datatype[json["event_name"]] == "inst_bytes":
            dasm_input += gemmini_decode(int(json["data"], 16)) + "|"
        elif event_to_datatype[json["event_name"]] == "inst_bytes":
            dasm_input += "DASM(" + json["data"] + ")|"
            inst_dump_list.append(json["data"])
        else:
            dasm_input += json["data"] + "|"
    dasm_input = dasm_input[:-1]
    p = Popen("$RISCV/bin/spike-dasm --isa=rv64gcv",  stdout=PIPE, stdin=PIPE, stderr=PIPE, text=True, shell=True)
    # if platform == "darwin":
    #     p = Popen("./spike-dasm --isa=rv64gcv",  stdout=PIPE, stdin=PIPE, stderr=PIPE, text=True, shell=True)
    # else:
    #     p = Popen("./spike-dasm.exe --isa=rv64gcv", stdout=PIPE, stdin=PIPE, stderr=PIPE, text=True, shell=True)
    stdout_data = p.communicate(input=dasm_input)[0]
    insts = stdout_data.split("|")
    print(insts)
    return np.array(insts)

inst_ids = np.array([int(inst_jsons[i]["id"], 16) for i in range(len(inst_jsons))])
inst_cycle = np.array([inst_jsons[i]["cycle"].strip() for i in range(len(inst_jsons))])
inst_event = np.array([inst_jsons[i]["event_name"] for i in range(len(inst_jsons))])
data_field = generate_data_array(inst_jsons)
# data_field = np.array([inst_jsons[i]["data"] for i in range(len(inst_jsons))])
inst_parent = np.array([int(inst_jsons[i]["parents"], 16) if inst_jsons[i]["parents"] != "None" else "None" for i in range(len(inst_jsons))])
print(len(data_field))
data = np.column_stack((inst_ids,inst_parent, inst_cycle, inst_event, data_field))
columns = ["inst_id", "parent_id", "cycle", "stage", "data"]

df = pd.DataFrame(data=data, columns=columns)

class InstructionTracer:
    def __init__(self, df):
        """
        Constructs NetworkX graph using inst_id and parent_id from GenEvent annotations as edges.

        Uniquify ID's allows for repeated Event IDs in the same instruction path.
        Used for user specified Event IDs that are passed to the parent of the next GenEvent
        Example: rob_id values in Gemmini can be used to uniquely identify instructions
        across events.
        """
        self.id = 0
        self.G = nx.DiGraph()
        df.sort_values(by=["cycle"])
        m = {}
        for row in df.itertuples():
            if row.inst_id in m:
                m[row.inst_id] = m[row.inst_id] + 1
            else:
                m[row.inst_id] = 0
            inst_id = str(row.inst_id) + "rev" + str(m[row.inst_id]) #Unique inst_id

            # self.G.add_node(inst_id, cycle=row.cycle, data=f"\"{row.data}\"", stage=f"\"{row.stage}\"")
            self.G.add_node(inst_id, cycle=row.cycle, data=row.data, stage=row.stage)
            if row.parent_id != "None":
                parent_id = str(row.parent_id) + "rev" + str(m[row.parent_id])
                if parent_id == inst_id:
                    parent_id = str(row.parent_id) + "rev" + str(m[row.parent_id] - 1)
                self.G.add_edge(parent_id, inst_id)
            
        #nx.drawing.nx_pydot.write_dot(self.G, ".sh")
        #import pygraphviz as pgv
        #G = pgv.AGraph("./graph.dot")  
        #G.layout(prog="dot")
        #G.draw("graph.png")


    def construct_speculative_trace(self):
        """Constructs instruction sequences through DFS of event graph"""
        self.id = 0
        paths = []
        for node in self.G:
            data = self.G.nodes[node]
            if self.G.in_degree(node) == 0: # root node
                new_paths = self.trace_down(node, [self.id], [])
                self.id += 1
                paths.extend(new_paths)
        for path in paths:
            if path[-1][0] not in end_stages:
                path.append(("FLUSH", int(path[-1][1]) + 1, "None"))
            else:
                path.append(("KONNATA_RET", int(path[-1][1]) + 1, "None"))

        return paths

    def trace_down(self, node, curr_path, paths):
        data = self.G.nodes[node]
        print(data)
        curr_path.append((data["stage"], int(data["cycle"]), data["data"]))
        if self.G.out_degree(node) == 0: # terminal node
            paths.append(curr_path)
            return paths
        succs = list(self.G.successors(node))
        for n in succs:
            paths.extend(self.trace_down(n, curr_path[:], []))
        return paths

tracer = InstructionTracer(df)
paths = tracer.construct_speculative_trace()
for item in paths:
    print(item)

def convert_to_kanata(threads, verbose=False):
    """Writes to Konata log file format from list of instruction sequences"""
    pq = []
    id = 0
    if not verbose:
        threads = list(filter(lambda x: x[-1][0] == 'KONNATA_RET', threads)) #Relies on the last element of inst list being RET
    for inst in threads:
        for stage in inst[1:]:
            heapq.heappush(pq, ((int(stage[1])), (id, stage[2], stage[0]))) #Min heap of (cycle -> (unique_id, data, pipeline stage))
        id += 1
            
    with open(args.output_file, 'w') as file:
        file.write('Kanata    0004\n')
        cycle, (id, data, stage) = heapq.heappop(pq)
        prev_cycle = cycle
        file.write(f'C=\t{cycle}\n')
        while pq:
            cycle_diff = cycle - prev_cycle
            if (cycle_diff > 0):
                file.write(f"C\t{cycle_diff}\n")
            if (stage in start_stages):
                file.write(f"I\t{id}\t{cycle}\t0\n")
            if (stage == 'KONNATA_RET'):
                file.write(f"R\t{id}\t{id}\t0\n")
            elif (stage == 'FLUSH'):
                file.write(f"R\t{id}\t{id}\t1\n")
            elif (event_to_datatype[stage] == "inst_bytes"):
                file.write(f"S\t{id}\t0\t{stage}\n")
                file.write(f"L\t{id}\t0\t{data}\\n\n")
                # file.write(f"L\t{id}\t1\t\\n{data}\n")
                # file.write(f"L\t{id}\t2\t\\n{data} \n")
            elif (event_to_datatype[stage] == "pc"):
                file.write(f"S\t{id}\t0\t{stage}\n")
                file.write(f"L\t{id}\t0\tPC:{data} \n")
            else:
                file.write(f"S\t{id}\t0\t{stage}\n")
                file.write(f"L\t{id}\t1\t\\n{data} \n")
                file.write(f"L\t{id}\t2\t\\n{data} \n")

            prev_cycle = cycle
            cycle, (id, data, stage) = heapq.heappop(pq)

convert_to_kanata(paths, verbose=True)
