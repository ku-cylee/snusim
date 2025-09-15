import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import tempfile
import time
import pyverilator
import tarfile
import zipfile
import io
import contextlib
import sys
from pathlib import Path

app = Flask(__name__)
socketio = SocketIO(app)

verilog_top_file = ""
verilog_build_dir = ""

frequency=10

IS_SIM_RUNNING = False
CONTINUE_SIM = True

register = {
    'time': 0,
    'cycle': 0,
    'segment': [0] * 42,
    'push_switch': [0] * 6,
    'dip_switch': [0] * 10,
    'led': [0] * 6,
    'lcd': [1] * 70
}

def sim_step(sim):
    if HAS_CLK:
        sim.io.CLK = not sim.io.CLK
    sim.eval()
    if HAS_CLK:
        sim.io.CLK = not sim.io.CLK
    sim.eval()

def write_registers(sim):
    # Update DIP Switch
    if HAS_DS:
        sim.io.DS = int(''.join(str(bit) for bit in register['dip_switch']), 2)

    # Update Push Switch
    if HAS_PS:
        sim.io.PS = int(''.join(str(bit) for bit in register['push_switch']), 2)

def read_registers(sim):
    register['time'] += 1
    
    # Update Seven Segment Display
    if HAS_SEG6:
        register['segment'][0:7] = [int(bit) for bit in format(sim.io.SEG6, f'0{7}b')]
    # Update Seven Segment Display
    if HAS_SEG5: 
        register['segment'][7:14] = [int(bit) for bit in format(sim.io.SEG5, f'0{7}b')]
    # Update Seven Segment Display
    if HAS_SEG4:
        register['segment'][14:21] = [int(bit) for bit in format(sim.io.SEG4, f'0{7}b')]
    # Update Seven Segment Display
    if HAS_SEG3:
        register['segment'][21:28] = [int(bit) for bit in format(sim.io.SEG3, f'0{7}b')]
    # Update Seven Segment Display
    if HAS_SEG2:
        register['segment'][28:35] = [int(bit) for bit in format(sim.io.SEG2, f'0{7}b')]
    # Update Seven Segment Display
    if HAS_SEG1:
        register['segment'][35:42] = [int(bit) for bit in format(sim.io.SEG1, f'0{7}b')]

    # Update LED
    if HAS_LED:
        register['led'] = [int(bit) for bit in format(sim.io.LED, f'0{6}b')]


def attribute_check(sim):
    if hasattr(sim, 'io'):
        io = getattr(sim, 'io')  # Get the 'io' attribute from sim
        if hasattr(io, 'CLK'):
            socketio.emit('info_update', {'message': '[Mapping] Port [CLK] is connected'})
            global HAS_CLK
            HAS_CLK = True
        if hasattr(io, 'SEG1'):
            socketio.emit('info_update', {'message': '[Mapping] Port [SEG1] is connected'})
            global HAS_SEG1
            HAS_SEG1 = True
        if hasattr(io, 'SEG2'):
            socketio.emit('info_update', {'message': '[Mapping] Port [SEG2] is connected'})
            global HAS_SEG2
            HAS_SEG2 = True
        if hasattr(io, 'SEG3'):
            socketio.emit('info_update', {'message': '[Mapping] Port [SEG3] is connected'})
            global HAS_SEG3
            HAS_SEG3 = True
        if hasattr(io, 'SEG4'):
            socketio.emit('info_update', {'message': '[Mapping] Port [SEG4] is connected'})
            global HAS_SEG4
            HAS_SEG4 = True
        if hasattr(io, 'SEG5'):
            socketio.emit('info_update', {'message': '[Mapping] Port [SEG5] is connected'})
            global HAS_SEG5
            HAS_SEG5 = True
        if hasattr(io, 'SEG6'):
            socketio.emit('info_update', {'message': '[Mapping] Port [SEG6] is connected'})
            global HAS_SEG6
            HAS_SEG6 = True
        if hasattr(io, 'LED'):
            socketio.emit('info_update', {'message': '[Mapping] Port [LED] is connected'})
            global HAS_LED
            HAS_LED = True
        if hasattr(io, 'DS'):
            socketio.emit('info_update', {'message': '[Mapping] Port [DS] is connected'})
            global HAS_DS
            HAS_DS = True
        if hasattr(io, 'PS'):
            socketio.emit('info_update', {'message': '[Mapping] Port [PS] is connected'})
            global HAS_PS
            HAS_PS = True
        if hasattr(io, 'LCD'):
            socketio.emit('info_update', {'message': '[Mapping] Port [LCD] is connected'})
            global HAS_LCD
            HAS_LCD = True

def simulation_thread():
    global HAS_CLK
    global HAS_DS
    global HAS_PS
    global HAS_SEG1
    global HAS_SEG2
    global HAS_SEG3
    global HAS_SEG4
    global HAS_SEG5
    global HAS_SEG6
    global HAS_LED
    global HAS_LCD

    HAS_CLK = False
    HAS_DS = False
    HAS_PS = False
    HAS_SEG1 = False
    HAS_SEG2 = False
    HAS_SEG3 = False
    HAS_SEG4 = False
    HAS_SEG5 = False
    HAS_SEG6 = False
    HAS_LED = False
    HAS_LCD = False

    for key in register:
        if isinstance(register[key], list):
        	register[key] = [0] * len(register[key])
        else:
            register[key] = 0


    try:
        sim = pyverilator.PyVerilator.build(verilog_top_file, verilog_path = [], build_dir = verilog_build_dir)

        attribute_check(sim)

        if HAS_CLK:
            sim.io.CLK = 0
        global CONTINUE_SIM
        CONTINUE_SIM = True
        global IS_SIM_RUNNING
        IS_SIM_RUNNING = True

        socketio.emit('info_update', {'message': '[INFO] Emulator is now Running... '})
        socketio.emit('info_update', {'message': '[INFO] CLK Speed is ' + str(frequency)+'Hz'})

        interval = 1/frequency  # 10 milliseconds in seconds

        # Track the next scheduled start time
        next_call_time = time.time()

        while CONTINUE_SIM:

            write_registers(sim)
            sim_step(sim)
            read_registers(sim)
            socketio.emit('segment_update', register['segment'])
            socketio.emit('led_update', register['led'])
            socketio.emit('lcd_update', register['lcd'])

            next_call_time += interval
            time_to_wait = next_call_time - time.time()

            if time_to_wait > 0:
                time.sleep(time_to_wait)

        IS_SIM_RUNNING = False

    except Exception as e:
        message = "Compilation Failure!"
        socketio.emit('info_update', {'message': message})
    
    socketio.emit('info_update', {'message': '[INFO] Killed Emulation...'})

@app.route('/upload_verilog_files', methods=['POST'])
def upload_files():

    socketio.emit('info_update', {'message': '[INFO] Uploading source files...'})
    verilog_source_path = tempfile.mkdtemp()

    global verilog_build_dir
    verilog_build_dir = verilog_source_path + "/build_obj"
    verilog_source_files = [] 

    files = request.files.getlist('files')
    for file in files:
        if file:
            filename = file.filename
            file_path = os.path.join(verilog_source_path, filename)
            file.save(file_path)

            if tarfile.is_tarfile(file_path):
                socketio.emit('info_update', {'message': "[INFO] Found tar file.. expanding"})
                with tarfile.open(file_path, 'r') as tar:
                    tar.extractall(path=verilog_source_path)
                    for member in tar.getmembers():
                        extracted_file_path = os.path.join(verilog_source_path, member.name)
                        if os.path.isfile(extracted_file_path) and extracted_file_path.endswith('.v'):
                            verilog_source_files.append(extracted_file_path)
                            socketio.emit('info_update', {'message': "[INFO] Extracting verilog source: " + member.name })

            elif zipfile.is_zipfile(file_path):
                socketio.emit('info_update', {'message': "[INFO] Found zip file.. expanding"})
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(verilog_source_path)
                    for extracted_file in zip_ref.namelist():
                        extracted_file_path = os.path.join(verilog_source_path, extracted_file)
                        if os.path.isfile(extracted_file_path) and extracted_file_path.endswith('.v'): 
                            verilog_source_files.append(extracted_file_path)
                            socketio.emit('info_update', {'message': "[INFO] Extracting verilog source: " + extracted_file })

            else:
                if file_path.endswith('.v'):
                    verilog_source_files.append(file_path)

    blist = [] 
    for bfile in verilog_source_files:
        blist.append(os.path.basename(bfile))

    socketio.emit('info_update', {'message': "[INFO] Verilog source list:" + str(blist) })
    

    #socketio.emit('info_update', {'message': "Uploaded Verilog Sources:" + str(verilog_source_files)})
    global verilog_top_file
    verilog_top_file = verilog_source_path + "/SNU_Emulator_Main_Entry.v"

    with open(verilog_top_file, 'w') as outfile:
        for fname in verilog_source_files:
            with open(fname) as infile:
                contents = infile.read()
                outfile.write(contents)
                outfile.write('\n')
                
    socketio.emit('info_update', {'message': 'Finished uploading verilog files...'})
    return jsonify({"file_paths": verilog_source_path})

@app.route('/start', methods=['POST'])
def start():
    global CONTINUE_SIM

    while IS_SIM_RUNNING:
        CONTINUE_SIM = False

    threading.Thread(target=simulation_thread).start()
    return jsonify("True")

@app.route('/stop', methods=['POST'])
def stop():
    global CONTINUE_SIM
    CONTINUE_SIM = False
    return jsonify("True")

@app.route('/set_frequency', methods=['POST'])
def set_frequency():
    data = request.get_json()
    global frequency
    frequency = int(data.get('frequency'))
    
    return jsonify({"status": "success", "frequency": frequency})


@app.route('/view', methods=['POST'])
def view():

    if verilog_top_file !='' and Path(verilog_top_file).exists():
        with open(verilog_top_file, "r") as file:
            buffer = ""
            for line_number, line in enumerate(file, start=1):
                buffer += f"{line_number}: {line}"
            socketio.emit('info_update', {'message': "[Source Code]:" + buffer })
    return jsonify("True")


@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('key_event')
def handle_key_event(json):
    key = json.get('key')
    event_type = json.get('event_type')

    if event_type == 'pressed':
        if key.isdigit():
            key_num = int(key)
            if 1 <= key_num <= 6:
                register['push_switch'][key_num - 1] = 1


    elif event_type == 'released':
        if key.isdigit():
            key_num = int(key)
            if 1 <= key_num <= 6:
                register['push_switch'][key_num - 1] = 0
            



@socketio.on('mouse_click')
def handle_mouse_click(json):
    element_id = json.get('element_id')
    
    if element_id == "dip_switch1_on" or element_id =="dip_switch1_off":
        register['dip_switch'][0] = int(not register['dip_switch'][0])
    elif element_id == "dip_switch2_on" or element_id =="dip_switch2_off":
        register['dip_switch'][1] = int(not register['dip_switch'][1])
    elif element_id == "dip_switch3_on" or element_id =="dip_switch3_off":
        register['dip_switch'][2] = int(not register['dip_switch'][2])
    elif element_id == "dip_switch4_on" or element_id =="dip_switch4_off":
        register['dip_switch'][3] = int(not register['dip_switch'][3])
    elif element_id == "dip_switch5_on" or element_id =="dip_switch5_off":
        register['dip_switch'][4] = int(not register['dip_switch'][4])
    elif element_id == "dip_switch6_on" or element_id =="dip_switch6_off":
        register['dip_switch'][5] = int(not register['dip_switch'][5])
    elif element_id == "dip_switch7_on" or element_id =="dip_switch7_off":
        register['dip_switch'][6] = int(not register['dip_switch'][6])
    elif element_id == "dip_switch8_on" or element_id =="dip_switch8_off":
        register['dip_switch'][7] = int(not register['dip_switch'][7])
    elif element_id == "dip_switch9_on" or element_id =="dip_switch9_off":
        register['dip_switch'][8] = int(not register['dip_switch'][8])
    elif element_id == "dip_switch10_on" or element_id =="dip_switch10_off":
        register['dip_switch'][9] = int(not register['dip_switch'][9])

    emit('dip_switch_update', register['dip_switch'], broadcast=True)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

