# Edge Impulse - OpenMV FOMO Object Detection Example
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2024 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE

import sensor, image, time, ml, math, uos, gc
import pyb
from pyb import UART
sensor.reset()                         # Reset and initialize the sensor.
sensor.set_pixformat(sensor.RGB565)    # Set pixel format to RGB565 (or GRAYSCALE)
sensor.set_framesize(sensor.QVGA)      # Set frame size to QVGA (320x240)
sensor.set_windowing((240, 240))       # Set 240x240 window.
sensor.skip_frames(time=2000)          # Let the camera adjust.
sensor.set_vflip(True) # the camera's upside down on the robot.
sensor.set_hmirror(True)
net = None
labels = None
min_confidence = 0.9
# initialize uart
uart = UART(1, 115200, timeout_char=100)\
# initialize GPIO
p = pyb.Pin("P3", pyb.Pin.OUT_PP)
# reduce exposure time for less blur
#sensor.set_auto_exposure(False, exposure_us=20000)  # ~8 ms
#thresholds
black_threshold = (0, 20, -128, 127, -128, 127)
red_threshold = (0, 100, 39, 127, -128, 127)
yellow_threshold = (0, 100, -60, 70, 0, 128)
green_threshold = (0, 100, -128, -3, -49, 45)
blue_threshold = (0, 100, -128, 127, -128, -23)
def in_threshold(L,A,B,c):
    if(c[0]<L<c[1] and c[2]<A<c[3] and c[4]<B<c[5]):
        return True
    else:
        return False
try:
    # load the model, alloc the model file on the heap if we have at least 64K free after loading
    net = ml.Model("trained.tflite", load_to_fb=uos.stat('trained.tflite')[6] > (gc.mem_free() - (64*1024)))
except Exception as e:
    raise Exception('Failed to load "trained.tflite", did you copy the .tflite and labels.txt file onto the mass-storage device? (' + str(e) + ')')

try:
    labels = [line.rstrip('\n') for line in open("labels.txt")]
except Exception as e:
    raise Exception('Failed to load "labels.txt", did you copy the .tflite and labels.txt file onto the mass-storage device? (' + str(e) + ')')

colors = [ # Add more colors if you are detecting more than 7 types of classes at once.
    (255,   0,   0),
    (  0, 255,   0),
    (255, 255,   0),
    (  0,   0, 255),
    (255,   0, 255),
    (  0, 255, 255),
    (255, 255, 255),
]

threshold_list = [(math.ceil(min_confidence * 255), 255)]

def fomo_post_process(model, inputs, outputs):
    ob, oh, ow, oc = model.output_shape[0]

    x_scale = inputs[0].roi[2] / ow
    y_scale = inputs[0].roi[3] / oh

    scale = min(x_scale, y_scale)

    x_offset = ((inputs[0].roi[2] - (ow * scale)) / 2) + inputs[0].roi[0]
    y_offset = ((inputs[0].roi[3] - (ow * scale)) / 2) + inputs[0].roi[1]

    l = [[] for i in range(oc)]

    for i in range(oc):
        img = image.Image(outputs[0][0, :, :, i] * 255)
        blobs = img.find_blobs(
            threshold_list, x_stride=1, y_stride=1, area_threshold=1, pixels_threshold=1
        )
        for b in blobs:
            rect = b.rect()
            x, y, w, h = rect
            score = (
                img.get_statistics(thresholds=threshold_list, roi=rect).l_mean() / 255.0
            )
            x = int((x * scale) + x_offset)
            y = int((y * scale) + y_offset)
            w = int(w * scale)
            h = int(h * scale)
            l[i].append((x, y, w, h, score))
    return l

clock = time.clock()
iterator = 0
while(True):

    clock.tick()
    iterator+=1
    img = sensor.snapshot().lens_corr(1.8)
    p.low()
    if iterator % 3==0:
        #continue
        img.to_grayscale()
        img.binary([(80,255)])

        blobs = img.find_blobs(
            [(0,20)],# must be a list of tuples
            pixel_threshold = 60,
            area_threshold=2500,
            merge=True
        )

        if blobs:
            uart.write("L")
        for b in blobs:
            width, height = b.w(), b.h()
            area = width*height
            filled_area = b.pixels()/area
            aspect = max(width,height)/min(width,height)

            if filled_area > 0.6 or filled_area<0.15:

                continue
            elif aspect > 1.6:

                continue
            elif area > 20000:
                continue
            else:
                img.draw_rectangle(b.rect(),0);

    else:
        circles = img.find_circles(threshold = 3500, r_min = 50) # find circles
        if circles:
            uart.write("c")
            time.sleep_ms(350)
        for circle in circles:
            img.draw_circle(circle.x(),circle.y(),circle.r()) # draw the circle for debugging

            sum = 0
            for i in range(1,6):
                colorarray = [0,0,0,0,0];

                for j in range(1,30):
                    x = circle.x()+math.floor(circle.r()*0.18*i*math.cos(math.radians(12*j)))
                    y = circle.y()-math.floor(circle.r()*0.18*i*math.sin(math.radians(12*j))) # increment across each ring.



                    r, g, b = img.get_pixel(x,y)


                    L,A,B = image.rgb_to_lab(r,g,b)

                    if r+g+b<100 and in_threshold(L,A,B,black_threshold):

                        colorarray[0] += 1

                    elif r>b and g > b and abs(g-r)<50 and in_threshold(L,A,B,yellow_threshold):
                        colorarray[1]+=1
                    elif r>g and r>b and in_threshold(L,A,B,red_threshold):
                        colorarray[2]+=1
                    elif g>r and g>b and in_threshold(L,A,B,green_threshold):
                        colorarray[3]+=1
                    elif b>g and b>r and in_threshold(L,A,B,blue_threshold):
                        colorarray[4]+=1
                color = colorarray.index(max(colorarray)) # voting
                if color == 0:
                    print("black")
                    sum += -2
                elif color == 1:
                    print("yellow")
                    sum += 0
                elif color == 2:
                    print("red")
                    sum+=-1
                elif color == 3:
                    print("green")
                    sum += 1;
                else:
                    print("blue")
                    sum += 2
                img.draw_circle(circle.x(),circle.y(),math.floor(circle.r()*0.18*i))
        print(sum)
        if sum == 2:
            uart.write("H") # harmed victim
            p.high()
        elif sum == 1:
            uart.write("S") #stable victim
            p.high()
        elif sum == 0:
            uart.write("U") # unharmed victim.
            p.high()
        print("_____________")
    for i, detection_list in enumerate(net.predict([img], callback=fomo_post_process)):
        if i == 0: continue  # background class
        if len(detection_list) == 0: continue  # no detections for this class?
        if iterator%3==0:

            print("********** %s **********" % labels[i])
            if(labels[i] == "H"):
                p.high()
                uart.write("H")
            elif(labels[i] == "S"):
                p.high()
                uart.write("S")
            elif(labels[i] == "U"):
                p.high()

                uart.write("U")
            print("********** %s **********" % labels[i])
        for x, y, w, h, score in detection_list:
            center_x = math.floor(x + (w / 2))
            center_y = math.floor(y + (h / 2))
            print(f"x {center_x}\ty {center_y}\tscore {score}")
            #img.draw_circle((center_x, center_y, 12), color=colors[i])


