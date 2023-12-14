from tkinter import *
from tkinter import ttk, font
from tkinter import filedialog as fd
import ctypes

import czifile
from czifile import CziFile

from xml.dom.minidom import parseString
import xml.dom.minidom

import numpy as npy
from PIL import Image, ImageTk

ctypes.windll.shcore.SetProcessDpiAwareness(1)
ScaleFactor=ctypes.windll.shcore.GetScaleFactorForDevice(0)

class RangeSlider(Frame):

    LINE_COLOUR = "#cccccc"
    LINE_WIDTH = 3
    HEAD_COLOUR_INNER = "#ffffff"
    HEAD_COLOUR_OUTER = "#cccccc"
    HEAD_RADIUS = 8
    HEAD_RADIUS_INNER = 6
    HEAD_LINE_WIDTH = 2

    def __init__(self, master, value_min=0, value_max=1, width=400, height=40,
                 value_display=lambda v: f"{v:0.2f}", inverse_display=lambda s: float(s),
                 value_in = 0, value_out = 1, command = None):
        
        Frame.__init__(self, master, height=height, width=width, bg = 'white')
        self.master = master
        self.user_moved_sliders_since_last_check = False

        self.__value_min = value_min
        self.__value_max = value_max
        self.__width = width
        self.__height = height
        self.__value_display = value_display
        self.__inverse_display = inverse_display

        # It is often necessary to translate the 'position', the x/y co-ordinates on the screen,
        # to and from the 'value', which the sliders are intended to represent.
        # The following functions are the only ones that handle such translations.
        self.__pos_to_value = None
        self.__value_to_pos = None

        self.__value_in = value_in
        self.__value_out = value_out

        self.__slider_x_start = RangeSlider.HEAD_RADIUS
        self.__slider_x_end = self.__width - RangeSlider.HEAD_RADIUS
        self.__slider_y = self.__height * 1 / 2
        self.__bar_offset = (-self.HEAD_RADIUS, -self.HEAD_RADIUS, self.HEAD_RADIUS, self.HEAD_RADIUS)
        self.__selected_head = None  # Bar selected for movement

        # Master canvas element and bindings to left mouse click and clicked move
        self.__canvas = Canvas(self, height=self.__height, width=self.__width, bg = 'white', bd = 0)
        self.__canvas.grid(row=0, padx = 50)
        self.__canvas.config(highlightthickness=0)
        self.__canvas.bind("<Motion>", self.__onclick)
        self.__canvas.bind("<B1-Motion>", self.__clicked_move)

        # Entries for showing user selected values, or allowing user to specify their own
        self.__entry_in_var = StringVar()
        self.__entry_in = ttk.Entry(self, width=len(value_display(value_in)), textvariable=self.__entry_in_var)
        self.__entry_in.grid(row=0, sticky=W, padx = 5)
        self.__entry_out_var = StringVar()
        self.__entry_out = ttk.Entry(self, width=len(value_display(value_out)), textvariable=self.__entry_out_var)
        self.__entry_out.grid(row=0, sticky=E, padx = 5)

        # Slider bar and heads
        self.__canvas.create_line((self.__slider_x_start, self.__slider_y, self.__slider_x_end, self.__slider_y),
                                  fill=RangeSlider.LINE_COLOUR, width=RangeSlider.LINE_WIDTH)
        self.__head_in = self.__add_head(value_in)
        self.__head_out = self.__add_head(value_out)

        # Reset in and out sliders and labels
        self.change_min_max(value_min, value_max, force=True, reset = False)
        self.change_display(value_display, inverse_display)
        self.__command = command

    def change_min_max(self, value_min, value_max, 
                       value_in = None, value_out = None, 
                       reset=True, force=False):
        """
        Update the minimum and maximum 'values', and adjust the slider heads if/as necessary.

        If the given min and max are unchanged, this function will do nothing unless the optional flag 'force' is True.
        When true (default), the optional flag 'reset' will reset in and out heads to min/max.
        Otherwise, they will be kept at their current value (not position) if possible.
        """
        if value_in != None: self.__value_in = value_in
        if value_out != None: self.__value_out = value_out
        if self.__value_min != value_min or self.__value_max != value_max or force:
            self.__value_min = value_min
            self.__value_max = value_max

            # Update pos-value conversion functions
            def pos_to_value(p):
                return value_min + (value_max - value_min) * (p - self.__slider_x_start) \
                       / (self.__slider_x_end - self.__slider_x_start)
            self.__pos_to_value = pos_to_value

            def value_to_pos(v):
                return self.__slider_x_start + (self.__slider_x_end - self.__slider_x_start) * (v - value_min) \
                       / (value_max - value_min)
            self.__value_to_pos = value_to_pos

            # Reset the sliders
            if reset:
                self.__value_in = value_min
                self.__value_out = value_max
            else:
                self.__value_in = min(max(self.__value_in, value_min), value_max)
                self.__value_out = max(min(self.__value_out, value_max), value_min)

            self.__move_head(self.__head_in, value_to_pos(self.__value_in))
            self.__move_head(self.__head_out, value_to_pos(self.__value_out))

            self.user_moved_sliders_since_last_check = False
            self.__update_entry_bindings()

    def change_display(self, value_display, inverse_display=None):
        """
        Update the function that returns the display text for a given 'value'.

        The single argument should be a function which accepts a single value
        and returns a string corresponding to the desired text.
        """

        self.__value_display = value_display
        self.__inverse_display = inverse_display

        if inverse_display:
            if inverse_display(value_display(self.__value_min)) != self.__value_min or \
                    inverse_display(value_display(self.__value_max)) != self.__value_max:
                self.__inverse_display = None

        label_in_text = self.__value_display(self.__value_in)
        self.__entry_in_var.set(label_in_text)
        self.__entry_in['width'] = max(self.__entry_in['width'], len(label_in_text))

        label_out_text = self.__value_display(self.__value_out)
        self.__entry_out_var.set(label_out_text)
        self.__entry_out['width'] = max(self.__entry_out['width'], len(label_out_text))

        self.__update_entry_bindings()

    @staticmethod
    def timestamp_display_builder(maximum_time_in_seconds=None):
        """
        A common-use-case utility function for passing to change_display to display timestamps.

        Returns a valid display function that will convert values in seconds to appropriate timestamps
        with relevant formatting and zero-padding for an optionally given maximum time.

        Example: my_range_slider.change_display(*RangeSlider.timestamp_display(2000))
        will generate labels of the form "##:##"
        """
        if not maximum_time_in_seconds or maximum_time_in_seconds > 3599:
            # Include space for 'hours'
            def timestamp_format(h, m, s):
                return f"{h}:{m:02}:{s:02}"
        else:
            def timestamp_format(h, m, s):
                return f"{h * 60 + m:02}:{s:02}"

        def f(total_seconds):
            hours, remaining_seconds = divmod(int(total_seconds), 3600)
            minutes, seconds = divmod(remaining_seconds, 60)
            return timestamp_format(hours, minutes, seconds)

        def inverse(timestamp):
            parts = timestamp.split(":")
            if len(parts) == 3:
                # Hours
                seconds = int(parts[0]) * 3600
            else:
                seconds = 0

            # Minutes and seconds
            seconds += int(parts[-2]) * 60 + int(parts[-1])
            return seconds

        return f, inverse

    def get_in_and_out(self) -> tuple:
        """
        Obtain the values of the 'in' and 'out' marks.
        Returns (in, out) as a tuple.
        """
        return self.__value_in, self.__value_out

    def __set_in_and_out(self, value_in, value_out) -> None:
        self.__value_in = value_in
        self.__value_out = value_out

    def have_sliders_moved(self) -> bool:
        """
        Whether the user has moved the sliders via slider or entry since the last
        time this function was called.
        """
        flag = self.user_moved_sliders_since_last_check
        self.user_moved_sliders_since_last_check = False
        return flag

    def __check_mouse_collision(self, x, y):
        """
        Check whether the mouse is clicked on either or both bar heads.
        Returns either one of the heads (self.__head_in or self.__head_out), True (both), or None.
        """

        def is_click_on_bbox(bbox, _x, _y):
            return bbox[0] < _x < bbox[2] and bbox[1] < _y < bbox[3]

        in_bbox = self.__canvas.bbox(self.__head_in[0])
        self.__selected_head = self.__head_in if is_click_on_bbox(in_bbox, x, y) else None

        out_bbox = self.__canvas.bbox(self.__head_out[0])
        if is_click_on_bbox(out_bbox, x, y):
            # If both could have been selected (close enough to overlap), return True
            self.__selected_head = True if self.__selected_head else self.__head_out

        return self.__selected_head

    def __onclick(self, event):
        """
        Handle behaviour when the left mouse button is clicked.
        """
        self.__selected_head = self.__check_mouse_collision(event.x, event.y)
        cursor = ("hand2" if self.__selected_head else "")
        self.__canvas.config(cursor=cursor)

    def __move_head(self, head: tuple, x):
        """
        Move the head element to the given x position.
        """
        r = RangeSlider.HEAD_RADIUS
        self.__canvas.coords(head[0], (x - r, self.__slider_y - r, x + r, self.__slider_y + r))
        r = RangeSlider.HEAD_RADIUS_INNER
        self.__canvas.coords(head[1], (x - r, self.__slider_y - r, x + r, self.__slider_y + r))

    def __clicked_move(self, event):
        """
        Handle movement of slider heads when the mouse is held with a head selected and moved.
        """
        if self.__selected_head:
            centre_x = min(self.__slider_x_end, max(self.__slider_x_start, event.x))
            if self.__selected_head is self.__head_in:
                centre_x = min(self.__value_to_pos(self.__value_out), centre_x)
                bar_value = self.__value_in = self.__pos_to_value(centre_x)
                self.__entry_in_var.set(self.__value_display(bar_value))
            elif self.__selected_head is self.__head_out:
                centre_x = max(self.__value_to_pos(self.__value_in), centre_x)
                bar_value = self.__value_out = self.__pos_to_value(centre_x)
                self.__entry_out_var.set(self.__value_display(bar_value))
            else:
                pos_out = self.__value_to_pos(self.__value_out)
                if centre_x > pos_out:
                    # Select the 'out' bar only when we're clearly pulling it right
                    self.__selected_head = self.__head_out
                else:
                    self.__selected_head = self.__head_in

            self.__move_head(self.__selected_head, centre_x)
            self.user_moved_sliders_since_last_check = True
            if self.__command != None: self.__command()

    def __add_head(self, value) -> tuple:
        """
        Create a 'head' of two circles at the given 'value'. Returns the IDs of both sub-elements in a tuple.
        """
        if self.__value_to_pos:
            centre_x = self.__value_to_pos(value)
        else:
            centre_x = self.__slider_x_end if value else self.__slider_x_start
        centre_y = self.__slider_y

        r = RangeSlider.HEAD_RADIUS
        outer = self.__canvas.create_oval(centre_x - r, centre_y - r,
                                          centre_x + r, centre_y + r,
                                          fill=RangeSlider.HEAD_COLOUR_OUTER,
                                          width=RangeSlider.HEAD_LINE_WIDTH, outline="", )

        r = RangeSlider.HEAD_RADIUS_INNER
        inner = self.__canvas.create_oval(centre_x - r, centre_y - r,
                                          centre_x + r, centre_y + r,
                                          fill=RangeSlider.HEAD_COLOUR_INNER,
                                          width=RangeSlider.HEAD_LINE_WIDTH, outline="", )

        return outer, inner

    def __update_entry_bindings(self):
        """
        Update the Entry bindings with functions that allow the user the user to move the heads by entering values.
        Only works if inverse_display is set. Should be called whenever the min/max values change.
        """
        def builder(this_var, this_head, other_var, other_head, parity):
            def f(*args):
                if self.__inverse_display:
                    value_in, value_out = self.get_in_and_out()
                    if parity == 1:
                        this_value, other = value_in, value_out
                    else:
                        this_value, other = value_out, value_in
                    proposed = self.__inverse_display(this_var.get())
                    if proposed != this_value:
                        # Value has changed
                        self.user_moved_sliders_since_last_check = True
                        this_value = min(max(self.__value_min, proposed), self.__value_max)
                        this_var.set(self.__value_display(this_value))

                        if this_value * parity > other * parity:
                            # Suppose user enters value for 'out' less than current 'in'
                            # Most intuitive behaviour would be to set 'in' at 'out'.
                            other = this_value
                            other_var.set(self.__value_display(other))
                            self.__move_head(other_head, self.__value_to_pos(other))
                        self.__move_head(this_head, self.__value_to_pos(this_value))

                        if parity == 1:
                            self.__set_in_and_out(this_value, other)
                        else:
                            self.__set_in_and_out(other, this_value)
            return f

        def do_binding(entry, f):
            entry.unbind('<FocusOut>')
            entry.unbind('<Return>')
            entry.unbind('<Escape>')

            entry.bind('<FocusOut>', f)
            entry.bind('<Return>', f)
            entry.bind('<Escape>', f)

        do_binding(self.__entry_in, builder(
            self.__entry_in_var, self.__head_in,
            self.__entry_out_var, self.__head_out, 1
        ))
        do_binding(self.__entry_out, builder(
            self.__entry_out_var, self.__head_out,
            self.__entry_in_var, self.__head_in, -1
        ))

        state = 'enabled' if self.__inverse_display else 'disabled'
        self.__entry_in['state'] = state
        self.__entry_out['state'] = state

class App(Tk):

    def __init__(self):

        Tk.__init__(self)

        # current open document
        self.opened_czi = None
        self.control_list = []
        self.histograms = []

        self.tk.call('tk', 'scaling', ScaleFactor / 75)
        self.title("CZI (Carl Zeiss Image) Composer")
        self.config(bg = "white")

        self.bold_font = font.Font(weight="bold", size = 10)

        # Create Frame widget
        self.left_frame = Frame(self, width = 400, height = 800)
        self.left_frame.grid(row = 0, column = 0, padx = 10, pady = 10)
        self.left_frame.config(bg = 'white')

        self.right_frame = Frame(self, width=800, height=800, bg='black')
        self.right_frame.grid(row = 0, column = 1, padx = 10, pady = 10)

        self.canvas = Canvas(self.right_frame, height = 800, width = 800, bg = 'white')
        self.canvas.grid(row = 0, column = 0)

        label = Label(self.left_frame, text="Channel mixer", width = 60, font = self.bold_font)
        label.grid(row = 1, column = 0)
        label.config(bg = 'white')

        self.canvas_histogram = Canvas(self.left_frame, width = 430, height = 150, bg = 'white')
        self.canvas_histogram.grid(row = 2, column = 0, padx = 10, pady = 20)

        self.channel_frame = Frame(self.left_frame)
        self.channel_frame.grid(row = 3, column = 0, padx = 0, pady = 10)
        self.channel_frame.config(bg = 'white')

        depth_label = Label(self.left_frame, text="Depth layers", width = 60, font = self.bold_font)
        depth_label.grid(row = 4, column = 0)
        depth_label.config(bg = 'white')

        self.depth_frame = Frame(self.left_frame)
        self.depth_frame.grid(row = 5, column = 0, padx = 10, pady = 10)
        self.depth_frame.config(bg = 'white')

        self.current_depth = IntVar()
        self.zstart = IntVar()
        self.zend = IntVar()

        label2 = Label(self.depth_frame, text="Current depth", justify = RIGHT)
        label2.grid(row = 0, column = 0, sticky = E)
        label2.config(bg = 'white')

        self.depth_slider = Scale(self.depth_frame, from_=0, to=1, orient='horizontal', 
                             command = self.update_z, 
                             variable = self.current_depth,
                             state = DISABLED, length = 250, tickinterval = 2)
        self.depth_slider.grid(row = 0, column = 1, padx = [30, 0])
        self.depth_slider.config(bg = 'white', highlightthickness=0)

        label3 = Label(self.depth_frame, text="")
        label3.grid(row = 1, column = 0, sticky = E)
        label3.config(bg = 'white')

        self.show_merge_variable = BooleanVar()
        self.show_merge_variable.set(False)
        self.show_merge = Checkbutton(self.depth_frame, text='Display merged image by Z axis', 
                                      variable = self.show_merge_variable,
                                      command = self.update_merged)
        self.show_merge.grid(row = 1, column = 1, padx = 0)
        self.show_merge.config(bg = 'white')
        
        label4 = Label(self.depth_frame, text="Z level (from)", justify = RIGHT)
        label4.grid(row = 3, column = 0, sticky = E)
        label4.config(bg = 'white')
        self.merge_z_from = Scale(self.depth_frame, from_=0, to=1, orient='horizontal', 
                             command = self.update_merged, 
                             variable = self.zstart,
                             state = DISABLED, length = 250, tickinterval = 2)
        self.merge_z_from.grid(row = 3, column = 1, padx = [30, 0])
        self.merge_z_from.config(bg = 'white', highlightthickness = 0)

        label5 = Label(self.depth_frame, text="Z level (to)", justify = RIGHT)
        label5.grid(row = 4, column = 0, sticky = E)
        label5.config(bg = 'white')
        self.merge_z_to = Scale(self.depth_frame, from_=0, to=1, orient='horizontal', 
                             command = self.update_merged, 
                             variable = self.zend,
                             state = DISABLED, length = 250, tickinterval = 2)
        self.merge_z_to.grid(row = 4, column = 1, padx = [30, 0])
        self.merge_z_to.config(bg = 'white', highlightthickness = 0)

        label6 = Label(self.depth_frame, text="Layer merge mode", justify = RIGHT)
        label6.grid(row = 2, column = 0, sticky = E, pady = [10, 20])
        label6.config(bg = 'white')
        self.merge_mode = StringVar()
        self.merge_mode.set('Maximum (Lighten)')
        self.merge_mode_combo = ttk.Combobox(self.depth_frame, 
                                             textvariable = self.merge_mode,
                                             values = (
                                                 'Maximum (Lighten)',
                                                 'Minimum (Darken)',
                                                 'Screen',
                                                 'Color Burn',
                                                 'Color Dodge',
                                                 'Linear Burn',
                                                 'Linear Dodge',
                                                 'Overlay',
                                                 'Hard Light',
                                                 'Soft Light',
                                                 'Vivid Light',
                                                 'Linear Light',
                                                 'Pin Light',
                                                 'Hard Mix',
                                                 'Difference',
                                                 'Exclusion',
                                                 'Substract',
                                                 'Multiply',
                                                 'Divide'))
        self.merge_mode_combo.grid(row = 2, column = 1, padx = 30, pady = [10, 20], sticky = 'w')

        self.menubar = Menu(self)
        self.config(menu = self.menubar)
        self.file_menu = Menu(self.menubar)

        self.file_menu.add_command(
            label = 'Open Carl Zeiss Image (CZI) ...',
            command = self.open_file
        )

        self.menubar.add_cascade(
            label="File",
            menu = self.file_menu
        )

        self.style = ttk.Style(self)
        self.style.theme_use('vista')

        self.left_frame.grid_remove()
        self.right_frame.grid_remove()

        self.startup = Label(self, text="Select CZI file", justify = CENTER, width = 75, font = self.bold_font)
        self.startup.grid(row = 0, column = 0, pady = 30)
        self.startup.config(bg = 'white')

        self.startup2 = Label(self, text=
"""This software aims to provide a light-weighted version (than ZEN/ZEN lite)
for simple reviewing and exporting task against Carl Zeiss image (CZI) files

Copyright (C) Z. Yang 2023""", 
                              justify = CENTER, width = 75)
        self.startup2.grid(row = 1, column = 0, pady = [0, 30])
        self.startup2.config(bg = 'white')

        self.resizable(False, False)
        self.eval('tk::PlaceWindow . center')
        self.mainloop()
        pass

    def open_file(self):

        first_open = (self.opened_czi == None)

        name = fd.askopenfilename()
        self.opened_czi = CziFile(name)
        self.channel_colors = []
        meta = self.opened_czi.metadata()
        self.np = czifile.imread(name)
        b, h, t, c, z, y, x, o = self.np.shape
        self.np = self.np[0,0,0,:,:,:,:,0] / 255.0 # c, z, y, x
        
        self.histograms = []
        for zid in range(z):
            zhist = []
            for cid in range(c):
                hist, _ = npy.histogram(self.np[cid, zid], 
                                        bins = [i / 255 for i in range(256)], 
                                        density = False)
                zhist += [hist]
            self.histograms += [zhist]
        
        if z > 1:
            self.depth_slider.config(state = NORMAL, to = z - 1)
            self.merge_z_from.config(state = NORMAL, to = z - 1)
            self.merge_z_to.config(state = NORMAL, to = z - 1)
        else:
            self.depth_slider.config(state = DISABLED, to = 1)
            self.merge_z_from.config(state = DISABLED, to = 1)
            self.merge_z_to.config(state = DISABLED, to = 1)
        
        for ctrlg in self.control_list:
            lbl, slider, canvas, check, _ = ctrlg
            lbl.destroy()
            slider.destroy()
            canvas.destroy()
            check.destroy()
        
        self.control_list = []
        self.channel_colors = []
        # initialize the channel selector
        for cid in range(c):
            DOMTree = xml.dom.minidom.parseString(meta)
            imgDocument = DOMTree.documentElement
            metadata = imgDocument.getElementsByTagName("Metadata")
            displaySetting = imgDocument.getElementsByTagName("DisplaySetting")
            channels = displaySetting[0].getElementsByTagName("Channels")
            channelArr = channels[0].getElementsByTagName("Channel")
            
            def hex2rgb(hexcolor):
                hexcolor = int(hexcolor, base=16) if isinstance(hexcolor, str) else hexcolor
                _rgb = ((hexcolor >> 16) & 0xff, (hexcolor >> 8) & 0xff, hexcolor & 0xff)
                return _rgb
            
            channelProp = channelArr[cid]
            if len(channelProp.getElementsByTagName("Color")) == 0:
                continue
            
            colorString = channelProp.getElementsByTagName("Color")[0].childNodes[0].data
            colorString = colorString[3:9]
            cr, cg, cb = hex2rgb(colorString)
            
            # init the default values
            low = 0 
            high = 1
            visible = True
            # FIXME: do not implement gamma function
            
            cr, cg, cb = (0, 0, 0)
            colorString = 'FFFFFF'
            shortname = 'Channel '+str(cid)
            if len(channelProp.getElementsByTagName("Color")) == 1:
                colorString = channelProp.getElementsByTagName("Color")[0].childNodes[0].data
                colorString = colorString[3:9]
                cr, cg, cb = hex2rgb(colorString)
            if len(channelProp.getElementsByTagName("Low")) == 1:
                low = float(channelProp.getElementsByTagName("Low")[0].childNodes[0].data)
            if len(channelProp.getElementsByTagName("ShortName")) == 1:
                shortname = channelProp.getElementsByTagName("ShortName")[0].childNodes[0].data
            if len(channelProp.getElementsByTagName("High")) == 1:
                high = float(channelProp.getElementsByTagName("High")[0].childNodes[0].data)
            if len(channelProp.getElementsByTagName("IsSelected")) == 1:
                visible = not (channelProp.getElementsByTagName("IsSelected")[0].childNodes[0].data == "false")
            
            self.channel_colors += [(cr, cg, cb, colorString)]

            label_channel_name = Label(self.channel_frame, text = shortname)
            label_channel_name.grid(row = cid, column = 0)
            label_channel_name.config(bg = 'white')
            
            slider = RangeSlider(self.channel_frame, 0, 1, value_in = low, value_out = high, width = 200,
                                 command = self.update_image)
            slider.grid(row = cid, column = 1, padx = 10)
            slider.config(bg = 'white')
            
            canvas = Canvas(self.channel_frame, width = 15, height = 15)
            canvas.grid(row = cid, column = 2, padx = 10)
            canvas.config(bg = '#' + colorString)
            
            is_layer_visible = BooleanVar()
            is_layer_visible.set(visible)
            check = Checkbutton(self.channel_frame, text='', variable = is_layer_visible,
                                command = self.update_image)
            check.grid(row = cid, column = 3, padx = 0)
            check.config(bg = 'white')
            
            self.control_list += [(label_channel_name, slider, canvas, check, is_layer_visible)]
            pass

        self.update_z(None)
        self.update_image()

        if first_open:
            self.startup.grid_remove()
            self.startup2.grid_remove()
            self.left_frame.grid()
            self.right_frame.grid()
            self.eval('tk::PlaceWindow . center')

            self.file_menu.add_command(
                label = 'Save current image ...',
                command = self.save_file
            )

        pass

    def save_file(self):
        fn = fd.asksaveasfilename(initialfile = 'export.png',
                                  defaultextension = '.png',
                                  filetypes = [('PNG file', '*.png'),
                                               ('JPEG file', '*.jpg'),
                                               ('Tagged image file format', '*.tiff')])
        self.image.save(fn)
        pass
    
    def update_merged(self, event = None):
        if not self.show_merge_variable.get():
            return
        
        startz = self.zstart.get()
        endz = self.zend.get()
        if startz < endz: zrange = range(startz, endz + 1, 1)
        if startz > endz: zrange = range(startz, endz - 1, -1)
        if startz == endz: zrange = [startz]

        c, _, y, x = self.np.shape
        rgb = npy.zeros((y, x, 3))
        
        mergenp = self.np[:, zrange[0], :, :] # c, y, x

        for zid in range(len(zrange) - 1):
            z = zrange[zid + 1]

            mode = self.merge_mode.get()
            modes = ('Maximum (Lighten)',
                     'Minimum (Darken)',
                     'Screen',
                     'Color Burn',
                     'Color Dodge',
                     'Linear Burn',
                     'Linear Dodge',
                     'Overlay',
                     'Hard Light',
                     'Soft Light',
                     'Vivid Light',
                     'Linear Light',
                     'Pin Light',
                     'Hard Mix',
                     'Difference',
                     'Exclusion',
                     'Substract',
                     'Multiply',
                     'Divide')
            
            this_layer = self.np[:, z, :, :]
            if mode == 'Maximum (Lighten)':
                mergenp = npy.maximum(mergenp, this_layer)
            elif mode == 'Minimum (Darken)':
                mergenp = npy.minimum(mergenp, this_layer)
            elif mode == 'Multiply':
                mergenp = mergenp * this_layer
            elif mode == 'Screen':
                mergenp = 1 - (1 - mergenp) * (1 - this_layer)
            elif mode == 'Color Burn':
                mergenp = 1 - (1 - mergenp) / (this_layer + 1e-5)
            elif mode == 'Color Dodge':
                mergenp = mergenp / (1 - this_layer + 1e-5)
            elif mode == 'Linear Burn':
                mergenp = this_layer + mergenp - 1
            elif mode == 'Linear Dodge':
                mergenp = this_layer + mergenp
            elif mode == 'Overlay':
                lt_mask = mergenp <= 0.5
                gt_mask = mergenp > 0.5
                mergenp[lt_mask] = (2 * this_layer * mergenp)[lt_mask]
                mergenp[gt_mask] = (1 - 2 * (1-this_layer) * (1-mergenp))[gt_mask]
            elif mode == 'Hard Light':
                lt_mask = this_layer <= 0.5
                gt_mask = this_layer > 0.5
                mergenp[lt_mask] = (2 * this_layer * mergenp)[lt_mask]
                mergenp[gt_mask] = (1 - 2 * (1-this_layer) * (1-mergenp))[gt_mask]
            elif mode == 'Soft Light':
                lt_mask = this_layer <= 0.5
                gt_mask = this_layer > 0.5
                mergenp[lt_mask] = (2 * this_layer * mergenp + mergenp * mergenp * (1 - 2 * this_layer))[lt_mask]
                mergenp[gt_mask] = (2 * mergenp * (1 - this_layer) + npy.sqrt(mergenp) * (2 * this_layer - 1))[gt_mask]
            elif mode == 'Vivid Light':
                lt_mask = this_layer <= 0.5
                gt_mask = this_layer > 0.5
                mergenp[lt_mask] = (1 + (mergenp - 1) / (2 * this_layer + 1e-5))[lt_mask]
                mergenp[gt_mask] = (mergenp / (2 * (1 - this_layer) + 1e-5))[gt_mask]
            elif mode == 'Linear Light':
                mergenp = 2 * this_layer + mergenp - 1
            elif mode == 'Pin Light':
                lt_mask = this_layer <= 0.5
                gt_mask = this_layer > 0.5
                mergenp[lt_mask] = (npy.minimum(2 * this_layer, mergenp))[lt_mask]
                mergenp[gt_mask] = (npy.maximum(2 * (this_layer - 0.5), mergenp))[gt_mask]
            elif mode == 'Hard Mix':
                gt_mask = this_layer + mergenp >= 1
                lt_mask = this_layer + mergenp < 1
                mergenp[lt_mask] = 0
                mergenp[gt_mask] = 1
            elif mode == 'Difference':
                mergenp = npy.abs(mergenp - this_layer)
            elif mode == 'Exclusion':
                mergenp = this_layer + mergenp - 2 * this_layer * mergenp
            elif mode == 'Substract':
                mergenp = mergenp - this_layer
            elif mode == 'Divide':
                mergenp = mergenp / (this_layer + 1e-5)
            
            mergenp[mergenp > 1] = 1
            mergenp[mergenp < 0] = 0

        for cid in range(c):
            
            _, slider, _, _, is_layer_visible = self.control_list[cid]
            low, high = slider.get_in_and_out()
            visible = is_layer_visible.get()

            linear = mergenp[cid,:,:] * 1
            if high > low:
                tk = 1 / (high - low)
                tb = - low * tk
                linear = tk * mergenp[cid,:,:] + tb
                linear[linear < 0] = 0
                linear[linear > 1] = 1
            else:
                linear[linear > high] = 1
                linear[linear <= high] = 0

            cr, cg, cb, _ = self.channel_colors[cid]

            if visible:
                rgb[:,:,0] += (cr / 255) * linear
                rgb[:,:,1] += (cg / 255) * linear
                rgb[:,:,2] += (cb / 255) * linear
        
        rgb[rgb > 1] = 1
        rgb[rgb < 0] = 0
        self.image = Image.fromarray(npy.uint8(rgb * 255))
        resized_image = self.image.resize((800, 800))

        self.tkimage = ImageTk.PhotoImage(resized_image)
        self.canvas.create_image(0, 0, anchor = NW, image = self.tkimage)

        pass

    def update_image(self):
        if self.show_merge_variable.get():
            self.update_merged()
            return
        
        z = self.current_depth.get() - 1
        c, _, y, x = self.np.shape
        rgb = npy.zeros((y, x, 3))

        for cid in range(c):
            
            _, slider, _, _, is_layer_visible = self.control_list[cid]
            low, high = slider.get_in_and_out()
            visible = is_layer_visible.get()

            linear = self.np[cid,z,:,:] * 1
            if high > low:
                tk = 1 / (high - low)
                tb = - low * tk
                linear = tk * self.np[cid,z,:,:] + tb
                linear[linear < 0] = 0
                linear[linear > 1] = 1
            else:
                linear[linear > high] = 1
                linear[linear <= high] = 0

            cr, cg, cb, _ = self.channel_colors[cid]

            if visible:
                rgb[:,:,0] += (cr / 255) * linear
                rgb[:,:,1] += (cg / 255) * linear
                rgb[:,:,2] += (cb / 255) * linear
            
        self.image = Image.fromarray(npy.uint8(rgb * 255))
        resized_image = self.image.resize((800, 800))

        self.tkimage = ImageTk.PhotoImage(resized_image)
        self.canvas.create_image(0, 0, anchor = NW, image = self.tkimage)

        pass
        
    def update_z(self, event):
        if self.show_merge_variable.get():
            return
        
        z = self.current_depth.get() - 1
        disp_w = self.canvas_histogram.winfo_reqwidth()
        disp_h = self.canvas_histogram.winfo_reqheight()
        item_w = disp_w / 256.0

        self.canvas_histogram.delete('all')

        channel = 0
        for chist in self.histograms[z]:
            points = [(0, disp_h)]
            i = 0
            for freq in chist:
                points += [(i * item_w, disp_h - disp_h * (npy.log10(freq + 1) / 6) )]
                i += 1
            
            points += [(disp_w, disp_h)]
            cr, cg, cb, ccolor = self.channel_colors[channel]
            hist_poly = self.canvas_histogram.create_polygon(*points, fill = '#' + ccolor)
            channel += 1
        
        self.update_image()
        pass

app = App()