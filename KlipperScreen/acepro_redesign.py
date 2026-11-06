"""ACE Pro KlipperScreen panel - redesign.

Subclasses the stock panel (acepro-any-klipper/KlipperScreen/acepro.py) and
keeps all of its Klipper/Moonraker plumbing (polling, gcode sending, status
parsing, toggles).  Only the user interface is new.  To roll back, point
KlipperScreen/panels/acepro.py at the stock file again.
"""
import importlib.util
import json
import logging
import math
import os
import threading
import time
import urllib.parse
import urllib.request

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango  # noqa: E402

def _find_base():
    env = os.environ.get("ACEPRO_BASE_PANEL")
    if env:
        return env
    here = os.path.realpath(__file__)
    sibling = os.path.join(os.path.dirname(here), "acepro.py")
    if os.path.exists(sibling) and os.path.realpath(sibling) != here:
        return sibling          # repo layout: stock panel next to this file
    return os.path.expanduser("~/acepro-any-klipper/KlipperScreen/acepro.py")


_BASE = _find_base()
_spec = importlib.util.spec_from_file_location("acepro_base_panel", _BASE)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

MOONRAKER = "http://127.0.0.1:7125"
BG, CARD, CARD2, TEXT, MUTED = "#0f1011", "#1a1b1d", "#232528", "#e8e6e1", "#8b9096"
GREEN, RED, AMBER, BLUE = "#19b36b", "#e8335c", "#e0a030", "#3a86e8"
BLADE_LIFE_CUTS = 1000
PRESETS = [("PLA", 45, 240), ("PETG", 55, 240), ("ABS/ASA", 65, 240),
           ("TPU", 45, 360), ("Nylon", 70, 480), ("Custom", None, None)]
SWATCHES = [(255, 255, 255), (0, 0, 0), (128, 128, 128), (234, 51, 35), (240, 135, 50), (250, 217, 74),
            (73, 163, 94), (84, 190, 252), (26, 70, 170), (130, 50, 220), (240, 115, 180), (130, 75, 30)]
FIL_STATES = [("bowden", "In the ACE", "The filament is still in the tube from the ACE."),
              ("splitter", "At the splitter", "It passed the hub but has not reached the toolhead."),
              ("toolhead", "At the toolhead", "The toolhead sensor sees it, but the nozzle is not loaded."),
              ("nozzle", "In the nozzle", "It is loaded and ready to print.")]


def hexcol(rgb):
    try:
        return "#%02x%02x%02x" % tuple(int(max(0, min(255, c))) for c in rgb)
    except Exception:
        return "#000000"


def rgba(rgb, a=1.0):
    return Gdk.RGBA(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, a)


def parse_hex(s):
    try:
        s = s.strip().lstrip("#")
        return [int(s[i:i + 2], 16) for i in (0, 2, 4)]
    except Exception:
        return None


class Panel(base.Panel):

    # ------------------------------------------------------------------ setup
    def create_main_screen(self):
        """Build the whole UI once; later calls only return to the home page."""
        self.current_view = "main"
        if getattr(self, "_ax_built", False):
            self._show("home")
            return
        self._ax_built = True
        self._ax_page = "home"
        self._ax_prev = "home"
        self._ax_dependents = []
        self.ax_extra = {i: {} for i in self.ace_instances}
        self.ax_state = {}
        self.ax_saved = {}
        self.ax_sel_tool = 0
        self.spool_selected_tool = 0
        self.ax_amount = 100
        self.ax_dryer_sel = "ALL"
        self.ax_dryer_temp = 45
        self.ax_dryer_dur = 240
        self.ax_edit = None
        self.ax_chain_tool = 0
        self.ax_chain_pick = []
        self.ax_check = {}
        self.ax_fil_state = "toolhead"
        self.ax_speed = {"feed": 60, "retract": 50, "plen": 50, "pspeed": 400}
        self.ax_confirm_state = None
        self.ax_poll_id = None
        self.ax_tc_active = False

        self._ax_portrait = self._is_portrait()
        try:
            h = min(Gdk.Screen.get_default().get_width(), Gdk.Screen.get_default().get_height())
        except Exception:
            h = 600
        self.ax_scale = 0.85 if h <= 480 else 1.0
        self._ax_css()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if self._ax_portrait
                       else Gtk.Orientation.HORIZONTAL, spacing=0)
        root.get_style_context().add_class("ax-root")
        self.ax_stack = Gtk.Stack()
        self.ax_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.ax_stack.set_hhomogeneous(False)
        self.ax_stack.set_vhomogeneous(False)
        self.ax_stack.set_hexpand(True)
        self.ax_stack.set_vexpand(True)

        # Navigation
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if self._ax_portrait
                      else Gtk.Orientation.VERTICAL, spacing=4)
        nav.set_homogeneous(True)
        nav.get_style_context().add_class("ax-nav")
        self.ax_nav_btns = {}
        for key, text in (("home", "Home"), ("tools", "Tools"), ("dryer", "Dryer"),
                          ("status", "Status"), ("check", "Print"), ("settings", "Settings")):
            b = Gtk.Button(label=text)
            b.get_style_context().add_class("ax-navbtn")
            b.connect("clicked", lambda _b, k=key: self._show(k))
            nav.pack_start(b, True, True, 0)
            self.ax_nav_btns[key] = b
        self.ax_nav = nav

        builders = [("home", self._build_home), ("slot", self._build_slot),
                    ("edit", self._build_edit), ("confirm", self._build_confirm),
                    ("progress", self._build_progress), ("tools", self._build_tools),
                    ("dryer", self._build_dryer), ("status", self._build_status),
                    ("check", self._build_check), ("settings", self._build_settings),
                    ("chain", self._build_chain), ("speeds", self._build_speeds),
                    ("position", self._build_position), ("numpad", self._build_numpad),
                    ("firmware", self._build_firmware)]
        for name, fn in builders:
            body = fn()
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            sw.set_kinetic_scrolling(True)
            sw.set_overlay_scrolling(False)
            sw.add(body)
            if name == "edit":
                sw.set_kinetic_scrolling(False)
            self.ax_stack.add_named(sw, name)

        if self._ax_portrait:
            root.pack_start(self.ax_stack, True, True, 0)
            root.pack_start(nav, False, False, 0)
        else:
            root.pack_start(nav, False, False, 0)
            root.pack_start(self.ax_stack, True, True, 0)
        self.ax_dependents = [self.ax_nav_btns[k] for k in ("home", "tools", "dryer", "status", "check")]
        self.content.add(root)
        self.content.show_all()
        self.ax_ck_card.set_visible(False)
        self._show("home")
        self._ax_start_poll()

    def add_custom_css(self):
        super().add_custom_css()

    def _ax_css(self):
        s = self.ax_scale
        px = lambda n: int(round(n * s))
        css = f"""
        .ax-root {{ background: {BG}; }}
        .ax-nav {{ background: #0b0c0d; padding: 4px; }}
        .ax-navbtn {{ background: {CARD}; color: {TEXT}; border-radius: 10px; border: none;
                     font-size: {px(14)}px; min-height: {px(44)}px; min-width: 0; padding: 0 {px(4)}px; }}
        .ax-navbtn.ax-on {{ background: {CARD2}; box-shadow: inset 0 -3px 0 {GREEN}; font-weight: bold; }}
        .ax-card {{ background: {CARD}; border-radius: 14px; padding: {px(10)}px; }}
        .ax-h1 {{ font-size: {px(26)}px; font-weight: bold; color: {TEXT}; }}
        .ax-h2 {{ font-size: {px(19)}px; font-weight: bold; color: {TEXT}; }}
        .ax-t {{ font-size: {px(16)}px; color: {TEXT}; }}
        .ax-m {{ font-size: {px(13)}px; color: {MUTED}; }}
        .ax-sec {{ font-size: {px(13)}px; color: {MUTED}; margin-top: {px(6)}px; }}
        .ax-ok {{ color: {GREEN}; }} .ax-bad {{ color: {RED}; }} .ax-warn {{ color: {AMBER}; }}
        .ax-btn {{ background: #090a0b; color: {TEXT}; border: none; border-radius: 12px;
                  font-size: {px(16)}px; min-height: {px(48)}px; padding: 0 {px(10)}px;
                  box-shadow: inset 0 -4px 0 #4a5057; }}
        .ax-btn.ax-small {{ min-height: {px(30)}px; font-size: {px(13)}px; padding: 0 {px(10)}px; }}
        .ax-btn:disabled {{ opacity: 0.4; }}
        .ax-btn.ax-green {{ background: {GREEN}; color: #04140c; font-weight: bold; box-shadow: inset 0 -4px 0 #0f7c4a; }}
        .ax-btn.ax-red {{ background: {RED}; color: #1a0309; font-weight: bold; box-shadow: inset 0 -4px 0 #a02040; }}
        .ax-btn.ax-amber {{ background: {AMBER}; color: #1f1402; font-weight: bold; box-shadow: inset 0 -4px 0 #9a6f1a; }}
        .ax-btn.ax-blue {{ box-shadow: inset 0 -4px 0 {BLUE}; }}
        .ax-btn.ax-sel {{ background: {CARD2}; box-shadow: inset 0 0 0 3px {GREEN}; font-weight: bold; }}
        .ax-slot {{ background: {CARD}; border: none; border-radius: 14px; padding: {px(8)}px; }}
        .ax-slot.ace_slot_loaded {{ box-shadow: inset 0 0 0 3px {GREEN}; }}
        .ax-slot.ace_slot_target {{ box-shadow: inset 0 0 0 3px {AMBER}; }}
        .ax-slot.ace_slot_empty {{ opacity: 0.55; }}
        .ax-dot {{ border-radius: 100px; min-width: {px(40)}px; min-height: {px(40)}px;
                  border: 3px solid #2d3033; }}
        .ax-sw {{ border-radius: 100px; min-width: {px(46)}px; min-height: {px(46)}px; padding: 0; border: 2px solid #2d3033; }}
        .ax-pill {{ background: {CARD}; border-radius: 100px; padding: 2px {px(10)}px;
                   font-size: {px(13)}px; color: {MUTED}; }}
        .ax-row {{ background: transparent; border-bottom: 1px solid #26282b; padding: {px(6)}px 0; }}
        scale trough {{ min-height: {px(10)}px; border-radius: 6px; background: #26282b; }}
        scale highlight {{ border-radius: 6px; background: {GREEN}; }}
        scale slider {{ min-width: {px(30)}px; min-height: {px(30)}px; border-radius: 100px;
                       background: {TEXT}; border: none; }}
        switch {{ min-height: {px(30)}px; }}
        """
        p = Gtk.CssProvider()
        p.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

    # ---------------------------------------------------------------- widgets
    def _lbl(self, text="", cls="ax-t", xalign=0.0, wrap=False, markup=False):
        l = Gtk.Label()
        if markup:
            l.set_markup(text)
        else:
            l.set_text(text)
        l.set_xalign(xalign)
        l.set_line_wrap(wrap)
        if wrap:
            l.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        l.get_style_context().add_class(cls)
        return l

    def _btn(self, text, cb=None, cls=""):
        b = Gtk.Button(label=text)
        b.get_style_context().add_class("ax-btn")
        for c in cls.split():
            b.get_style_context().add_class(c)
        if cb:
            b.connect("clicked", lambda _b: cb())
        return b

    def _card(self, child=None, spacing=6):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        box.get_style_context().add_class("ax-card")
        if child is not None:
            box.pack_start(child, True, True, 0)
        return box

    def _page(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(b, "set_margin_" + m)(8)
        b.get_style_context().add_class("ax-root")
        return b

    def _hrow(self, *widgets, homogeneous=False, spacing=8):
        r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
        r.set_homogeneous(homogeneous)
        for w in widgets:
            r.pack_start(w, True, True, 0)
        return r

    def _switch_row(self, title, sub, switch):
        r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        r.get_style_context().add_class("ax-row")
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        v.pack_start(self._lbl(title), False, False, 0)
        v.pack_start(self._lbl(sub, "ax-m", wrap=True), False, False, 0)
        r.pack_start(v, True, True, 0)
        switch.set_valign(Gtk.Align.CENTER)
        r.pack_end(switch, False, False, 0)
        return r

    def _show(self, name):
        if name not in ("slot", "edit", "confirm", "numpad", "progress"):
            self._ax_prev = name
        self._ax_page = name
        self.ax_stack.set_visible_child_name(name)
        for k, b in self.ax_nav_btns.items():
            sc = b.get_style_context()
            if k == name:
                sc.add_class("ax-on")
            else:
                sc.remove_class("ax-on")
        if name == "slot":
            self._refresh_slot_sheet()
        elif name == "dryer":
            self._refresh_dryer()
        elif name == "status":
            self._refresh_status()
        elif name == "check":
            self._check_refresh_files()
        elif name == "chain":
            self._refresh_chain()
        elif name == "position":
            self._refresh_position()
        elif name == "settings":
            self._refresh_settings()
        elif name == "tools":
            self._refresh_tools()
        elif name == "speeds":
            self._refresh_speeds()
        elif name == "firmware":
            self._refresh_firmware()

    def on_back(self):
        if self._ax_page in ("slot", "edit", "confirm", "numpad", "chain", "speeds",
                             "position", "firmware", "progress"):
            self._show(self._ax_prev if self._ax_page in ("slot", "confirm", "numpad", "progress")
                       else ("settings" if self._ax_page in ("chain", "speeds", "firmware")
                             else ("status" if self._ax_page == "position" else "home")))
            return True
        if self._ax_page != "home":
            self._show("home")
            return True
        return False

    def return_to_main_screen(self):
        self._show("home")
        return False

    # ------------------------------------------------------------------- home
    def _build_home(self):
        page = self._page()
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.conn_status_label = Gtk.Label()
        self.conn_status_label.get_style_context().add_class("ax-pill")
        self.ax_pill_dryer = self._lbl("Dryer off", "ax-pill")
        self.ax_pill_endless = self._lbl("Endless off", "ax-pill")
        for w in (self.conn_status_label, self.ax_pill_dryer, self.ax_pill_endless):
            top.pack_start(w, False, False, 0)
        self.ax_unit_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        top.pack_end(self.ax_unit_box, False, False, 0)
        page.pack_start(top, False, False, 0)
        srow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_label = self._lbl("ACE: ...", "ax-m")
        srow.pack_start(self.status_label, True, True, 0)
        rb = self._btn("Refresh", lambda: self.refresh_status(None))
        rb.get_style_context().add_class("ax-small")
        srow.pack_end(rb, False, False, 0)
        page.pack_start(srow, False, False, 0)

        # slots + filament path
        self.ax_slot_holder = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL if self._ax_portrait else Gtk.Orientation.VERTICAL,
            spacing=6)
        self.ax_slot_holder.set_homogeneous(True)
        self.ax_path = Gtk.DrawingArea()
        self.ax_path.set_size_request(-1 if not self._ax_portrait else 1,
                                      int(220 * self.ax_scale) if self._ax_portrait else 1)
        self.ax_path.set_hexpand(True)
        self.ax_path.set_vexpand(True)
        self.ax_path.connect("draw", self._draw_path)
        if self._ax_portrait:
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            body.pack_start(self.ax_slot_holder, False, False, 0)
            body.pack_start(self.ax_path, True, True, 0)
        else:
            body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            self.ax_slot_holder.set_size_request(int(220 * self.ax_scale), -1)
            body.pack_start(self.ax_slot_holder, False, False, 0)
            body.pack_start(self.ax_path, True, True, 0)
        page.pack_start(body, True, True, 0)

        acts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        acts.set_homogeneous(True)
        self.ax_btn_load = self._btn("Load", self._home_load, "ax-green")
        self.ax_btn_unload = self._btn("Unload", self._home_unload, "ax-red")
        acts.pack_start(self.ax_btn_load, True, True, 0)
        acts.pack_start(self.ax_btn_unload, True, True, 0)
        acts.pack_start(self._btn("Dryer", lambda: self._show("dryer"), "ax-blue"), True, True, 0)
        acts.pack_start(self._btn("More", lambda: self._show("tools"), "ax-blue"), True, True, 0)
        page.pack_start(acts, False, False, 0)
        self._rebuild_slots()
        self._rebuild_unit_tabs()
        return page

    def _rebuild_unit_tabs(self):
        for c in self.ax_unit_box.get_children():
            self.ax_unit_box.remove(c)
        if len(self.ace_instances) > 1:
            for i in self.ace_instances:
                b = self._btn(f"ACE {i}", lambda i=i: self._select_instance(i),
                              "ax-sel" if i == self.current_instance else "")
                self.ax_unit_box.pack_start(b, False, False, 0)
        self.ax_unit_box.show_all()

    def _select_instance(self, i):
        self.current_instance = i
        self._rebuild_slots()
        self._rebuild_unit_tabs()
        inv = self.instance_data[i]["inventory"]
        self.update_slots_from_data(i, [dict(s) for s in inv])
        self.ax_path.queue_draw()

    def _rebuild_slots(self):
        inst = self.instance_data[self.current_instance]
        for c in self.ax_slot_holder.get_children():
            self.ax_slot_holder.remove(c)
        for k in ("slot_buttons", "slot_labels", "slot_color_boxes", "slot_tool_labels"):
            inst[k] = []
        inst["slot_gear_buttons"] = []
        for i in range(4):
            gt = inst["tool_offset"] + i
            b = Gtk.Button()
            b.get_style_context().add_class("ax-slot")
            if self._ax_portrait:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            else:
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            dot = Gtk.Box()
            dot.get_style_context().add_class("ax-dot")
            dot.set_halign(Gtk.Align.CENTER)
            dot.set_valign(Gtk.Align.CENTER)
            tl = Gtk.Label()
            tl.get_style_context().add_class("ax-h2")
            ml = Gtk.Label(label="Empty\n ")
            ml.get_style_context().add_class("ax-m")
            ml.set_justify(Gtk.Justification.CENTER if self._ax_portrait else Gtk.Justification.LEFT)
            txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            tl.set_xalign(0.5 if self._ax_portrait else 0.0)
            ml.set_xalign(0.5 if self._ax_portrait else 0.0)
            txt.pack_start(tl, False, False, 0)
            txt.pack_start(ml, False, False, 0)
            box.pack_start(dot, False, False, 0)
            box.pack_start(txt, True, True, 0)
            b.add(box)
            b.connect("clicked", lambda _b, ii=i: self._open_slot(self.current_instance, ii))
            self.ax_slot_holder.pack_start(b, True, True, 0)
            inst["slot_buttons"].append(b)
            inst["slot_labels"].append(ml)
            inst["slot_color_boxes"].append(dot)
            inst["slot_tool_labels"].append(tl)
        self.ax_slot_holder.show_all()

    def _tool_for(self, instance_id, local):
        return self.instance_data[instance_id]["tool_offset"] + local

    def _loc_for_tool(self, tool):
        for iid in self.ace_instances:
            off = self.instance_data[iid]["tool_offset"]
            if off <= tool < off + 4:
                return iid, tool - off
        return None, None

    def _open_slot(self, iid, local):
        if not self._require_ready_slot(iid, local):
            return
        self.ax_slot_sel = (iid, local)
        self.ax_sel_tool = self._tool_for(iid, local)
        self._show("slot")

    def _home_load(self):
        self._open_first_ready(load=True)

    def _home_unload(self):
        cur = self.get_current_loaded_slot()
        if cur is None or cur < 0:
            self._screen.show_popup_message("No tool is loaded.", 1)
            return
        iid, local = self._loc_for_tool(cur)
        if iid is None:
            self._send_gcode("UNLOAD_TOOL")
            return
        self.ax_slot_sel = (iid, local)
        self.show_unload_confirmation(iid, cur)

    def _open_first_ready(self, load=True):
        cur = self.get_current_loaded_slot()
        for iid in self.ace_instances:
            for local in range(4):
                if self._slot_is_ready(iid, local) and self._tool_for(iid, local) != cur:
                    self._open_slot(iid, local)
                    return
        self._screen.show_popup_message("No other ready slot. Load filament into a slot first.", 2)

    # ------------------------------------------------------ inherited updates
    def update_slot_loaded_states(self):
        super().update_slot_loaded_states()
        try:
            for iid in self.ace_instances:
                inst = self.instance_data[iid]
                if not inst["slot_buttons"]:
                    continue
            if hasattr(self, "ax_path"):
                self.ax_path.queue_draw()
            self._ax_update_pills()
            if getattr(self, "_ax_page", "") == "slot":
                self._refresh_slot_sheet()
        except Exception:
            logging.debug("ACE: ax update failed", exc_info=True)

    def update_slots_from_data(self, instance_id, slot_data):
        super().update_slots_from_data(instance_id, slot_data)

    def _set_slot_visual_state(self, instance_id, local_slot, is_ready):
        try:
            inst = self.instance_data[instance_id]
            sb = inst["slot_buttons"][local_slot]
            sb.set_opacity(1.0 if is_ready else 0.55)
        except Exception:
            pass

    def _format_tool_label_markup(self, global_tool, slot_data, loaded=False):
        rfid = " <small>RFID</small>" if slot_data.get("rfid") else ""
        col = GREEN if loaded else TEXT
        return f'<span foreground="{col}"><b>T{global_tool}</b></span>{rfid}'

    def _update_connection_status_label(self):
        l = getattr(self, "conn_status_label", None)
        if l is None:
            return
        bad = None
        unknown = False
        for iid in self.ace_instances:
            st = self.instance_data[iid].get("connection_state")
            if st is None:
                unknown = True
            elif st != "connected":
                bad = bad or f"ACE {iid}: {st}"
        if bad:
            l.set_markup(f'<span foreground="{AMBER}">{bad}</span>')
        elif unknown:
            l.set_markup(f'<span foreground="{MUTED}">Checking...</span>')
        else:
            l.set_markup(f'<span foreground="{GREEN}">Connected</span>')

    def _ax_update_pills(self):
        try:
            on = [i for i in self.ace_instances
                  if (self.ax_extra.get(i, {}).get("dryer_status") or {}).get("status") == "drying"]
            self.ax_pill_dryer.set_text("Dryer on" if on else "Dryer off")
            self.ax_pill_endless.set_text("Endless on" if self.endless_spool_enabled
                                          else "Endless off")
            tc = self.target_tool_index
            cur = self.get_current_loaded_slot()
            if self.ax_state.get("toolchange_in_progress"):
                self.status_label.set_text(f"ACE: Toolchange to T{tc}...")
            elif tc != -1 and tc != cur:
                self.status_label.set_text(f"ACE: Toolchange to T{tc} unconfirmed")
            elif cur != -1:
                self.status_label.set_text(f"ACE: Tool T{cur} Loaded")
            else:
                self.status_label.set_text("ACE: No Tool Loaded")
            ld = cur != -1
            self.ax_btn_unload.set_sensitive(ld)
        except Exception:
            pass

    def _update_ace_pro_sensitivity(self, enabled):
        for w in self.ax_dependents:
            w.set_sensitive(bool(enabled))
        for attr in ("ax_stack_dep",):
            pass
        for w in getattr(self, "ax_settings_dep", []):
            w.set_sensitive(bool(enabled))
        if not enabled and self._ax_page not in ("settings",):
            self._show("settings")

    def _update_ace_pro_switch_lock(self):
        try:
            state = self._printer.state
        except Exception:
            state = "ready"
        locked = state in ("printing", "paused")
        w = getattr(self, "ace_pro_control", None)
        if w is not None:
            w.set_sensitive(not locked)
            w.set_opacity(0.45 if locked else 1.0)

    def _set_match_mode_ui(self, mode, update_widget=True):
        if mode not in ("exact", "material", "next"):
            mode = "exact"
        self.ax_match_mode = mode
        for k, b in getattr(self, "ax_match_btns", {}).items():
            sc = b.get_style_context()
            (sc.add_class if k == mode else sc.remove_class)("ax-sel")

    def _update_match_mode_sensitivity(self):
        for b in getattr(self, "ax_match_btns", {}).values():
            b.set_sensitive(bool(self.endless_spool_enabled))
        self._ax_update_pills()

    def on_match_mode_selected(self, mode):
        self._set_match_mode_ui(mode)
        self._send_gcode(f"ACE_SET_ENDLESS_SPOOL_MODE MODE={mode}")
        names = {"exact": "Exact (material + color)", "material": "Same material only",
                 "next": "Next ready spool"}
        self._screen.show_popup_message(f"Match mode: {names[mode]}", 1)

    # --------------------------------------------------------- filament path
    def _draw_path(self, area, cr):
        w, h = area.get_allocated_width(), area.get_allocated_height()
        inst = self.instance_data[self.current_instance]
        cur = self.get_current_loaded_slot()
        off = inst["tool_offset"]
        loaded = cur - off if off <= cur < off + 4 else -1
        port = self._ax_portrait
        s = self.ax_scale

        def col(i):
            c = inst["inventory"][i].get("color") or [90, 90, 90]
            return [x / 255.0 for x in c]

        def line(pts, rgb, width):
            cr.set_source_rgb(*rgb)
            cr.set_line_width(width)
            cr.set_line_cap(1)
            cr.move_to(*pts[0])
            for p in pts[1:]:
                if len(p) == 6:
                    cr.curve_to(*p)
                else:
                    cr.line_to(*p)
            cr.stroke()

        def text(x, y, t, size, rgb, bold=False, align="l"):
            cr.set_source_rgb(*rgb)
            cr.select_font_face("DejaVu Sans", 0, 1 if bold else 0)
            cr.set_font_size(size * s)
            ext = cr.text_extents(t)
            if align == "c":
                x -= ext.width / 2
            elif align == "r":
                x -= ext.width
            cr.move_to(x, y)
            cr.show_text(t)

        dim = (0.2, 0.22, 0.24)
        tcol = (0.91, 0.9, 0.88)
        mcol = (0.55, 0.57, 0.59)
        lc = col(loaded) if loaded >= 0 else (0.1, 0.7, 0.42)
        rdm, th = bool(self.rdm_sensor), bool(self.toolhead_sensor)
        if port:
            n = 4
            xs = [(i + 0.5) * w / n for i in range(n)]
            y0, hub_y = 6, h * 0.34
            cx = w / 2
            ys = [hub_y + (h - hub_y) * f for f in (0, 0.38, 0.72)]
            ny = h - 22
            for i in range(n):
                if i != loaded:
                    line([(xs[i], y0), (xs[i], y0 + 20), (xs[i], hub_y - 20, cx, hub_y - 30, cx, hub_y)], dim, 4)
            line([(cx, hub_y), (cx, ny)], dim, 4)
            if loaded >= 0:
                line([(xs[loaded], y0), (xs[loaded], y0 + 20),
                      (xs[loaded], hub_y - 20, cx, hub_y - 30, cx, hub_y), (cx, ny)], lc, 9)
            cr.set_source_rgb(*lc)
            cr.rectangle(cx - 14, hub_y - 7, 28, 22)
            cr.fill()
            text(cx + 24, hub_y + 8, "Hub", 15, tcol, True)
            for y, on, lab in ((ys[1], rdm, "RDM sensor"), (ys[2], th, "Toolhead sensor")):
                cr.new_sub_path()
                cr.arc(cx, y, 11, 0, 6.3)
                cr.set_source_rgb(*(lc if on else (0.06, 0.07, 0.07)))
                cr.fill_preserve()
                cr.set_source_rgb(*(lc if on else (0.29, 0.31, 0.34)))
                cr.set_line_width(4)
                cr.stroke()
                text(cx + 24, y + 5, lab, 15, tcol, True)
                text(cx + 24, y + 22, "filament seen" if on else "clear", 12, mcol)
            text(cx + 24, ny + 5, "Nozzle", 15, tcol, True)
        else:
            n = 4
            ys = [(i + 0.5) * h / n for i in range(n)]
            cy = h / 2
            hubx, rx, tx, nx = w * 0.52, w * 0.68, w * 0.82, w - 40
            for i in range(n):
                if i != loaded:
                    line([(0, ys[i]), (w * 0.22, ys[i]), (w * 0.38, ys[i], w * 0.38, cy, hubx, cy)], dim, 4)
            line([(hubx, cy), (nx, cy)], dim, 4)
            if loaded >= 0:
                line([(0, ys[loaded]), (w * 0.22, ys[loaded]),
                      (w * 0.38, ys[loaded], w * 0.38, cy, hubx, cy), (nx, cy)], lc, 9)
            cr.set_source_rgb(*lc)
            cr.rectangle(hubx - 8, cy - 18, 16, 36)
            cr.fill()
            text(hubx, cy - 28, "Hub", 15, tcol, True, "c")
            for x, on, lab, up in ((rx, rdm, "RDM", False), (tx, th, "Toolhead", True)):
                cr.new_sub_path()
                cr.arc(x, cy, 11, 0, 6.3)
                cr.set_source_rgb(*(lc if on else (0.06, 0.07, 0.07)))
                cr.fill_preserve()
                cr.set_source_rgb(*(lc if on else (0.29, 0.31, 0.34)))
                cr.set_line_width(4)
                cr.stroke()
                yy = cy - 34 if up else cy + 34
                text(x, yy, lab, 14, tcol, True, "c")
                text(x, yy + 16, "seen" if on else "clear", 12, mcol, False, "c")
            text(nx, cy + 44, "Nozzle", 14, tcol, True, "c")
        return False

    # ------------------------------------------------------------ slot sheet
    def _build_slot(self):
        page = self._page()
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.ax_sl_dot = Gtk.Box()
        self.ax_sl_dot.get_style_context().add_class("ax-dot")
        self.ax_sl_dot.set_size_request(int(56 * self.ax_scale), int(56 * self.ax_scale))
        self.ax_sl_dot.set_valign(Gtk.Align.CENTER)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.ax_sl_title = self._lbl("", "ax-h1")
        self.ax_sl_sub = self._lbl("", "ax-m")
        self.ax_sl_chip = self._lbl("", "ax-m")
        for w in (self.ax_sl_title, self.ax_sl_sub, self.ax_sl_chip):
            v.pack_start(w, False, False, 0)
        head.pack_start(self.ax_sl_dot, False, False, 0)
        head.pack_start(v, True, True, 0)
        page.pack_start(head, False, False, 0)
        self.ax_sl_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self._card(self.ax_sl_rows), False, False, 0)
        self.ax_sl_main = self._btn("Load", self._slot_main, "ax-green")
        self.ax_sl_feed = self._btn("Feed assist", self._slot_feed_assist, "ax-blue")
        r1 = self._hrow(self.ax_sl_main, self._btn("Edit slot", self._slot_edit, "ax-blue"), homogeneous=True)
        r2 = self._hrow(self.ax_sl_feed, self._btn("Test slot", self._slot_test, "ax-blue"), homogeneous=True)
        page.pack_start(r1, False, False, 0)
        page.pack_start(r2, False, False, 0)
        page.pack_start(self._btn("Close", lambda: self._show("home")), False, False, 0)
        return page

    def _kv(self, k, v):
        r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        r.get_style_context().add_class("ax-row")
        r.pack_start(self._lbl(k, "ax-m"), True, True, 0)
        r.pack_end(self._lbl(v, "ax-t", 1.0), False, False, 0)
        return r

    def _refresh_slot_sheet(self):
        sel = getattr(self, "ax_slot_sel", None)
        if not sel:
            return
        iid, local = sel
        inv = self.instance_data[iid]["inventory"][local]
        tool = self._tool_for(iid, local)
        cur = self.get_current_loaded_slot()
        self.ax_sl_dot.override_background_color(Gtk.StateFlags.NORMAL, rgba(inv.get("color") or [0, 0, 0]))
        self.ax_sl_title.set_text(f"T{tool} · {inv.get('material') or 'Empty'}")
        self.ax_sl_sub.set_text(f"Slot {local + 1} of ACE {iid}")
        loaded = cur == tool
        self.ax_sl_chip.set_markup(
            f'<span foreground="{GREEN}">● Loaded in the toolhead</span>' if loaded
            else ('<span foreground="%s">● Toolchange unconfirmed</span>' % AMBER
                  if self.target_tool_index == tool else "Ready"))
        for c in self.ax_sl_rows.get_children():
            self.ax_sl_rows.remove(c)
        for k, v in (("Material", inv.get("material") or "-"),
                     ("Nozzle", f"{inv.get('temp', 0)} °C"),
                     ("Color", hexcol(inv.get("color") or [0, 0, 0])),
                     ("RFID", "yes" if inv.get("rfid") else "no")):
            self.ax_sl_rows.pack_start(self._kv(k, v), False, False, 0)
        self.ax_sl_rows.show_all()
        self.ax_sl_main.set_label("Unload" if loaded else "Load")
        sc = self.ax_sl_main.get_style_context()
        sc.remove_class("ax-green")
        sc.remove_class("ax-red")
        sc.add_class("ax-red" if loaded else "ax-green")
        fa = self.ax_extra.get(iid, {}).get("feed_assist_slot", -1)
        self.ax_sl_feed.set_label("Feed assist: On" if fa == local else "Feed assist: Off")

    def _slot_main(self):
        iid, local = self.ax_slot_sel
        tool = self._tool_for(iid, local)
        if self.get_current_loaded_slot() == tool:
            self.show_unload_confirmation(iid, tool)
        else:
            self.show_load_confirmation(iid, tool)

    def _slot_feed_assist(self):
        iid, local = self.ax_slot_sel
        tool = self._tool_for(iid, local)
        on = self.ax_extra.get(iid, {}).get("feed_assist_slot", -1) == local
        self._send_gcode(f"ACE_{'DISABLE' if on else 'ENABLE'}_FEED_ASSIST T={tool}")
        self.ax_extra.setdefault(iid, {})["feed_assist_slot"] = -1 if on else local
        self._refresh_slot_sheet()

    def _slot_test(self):
        iid, local = self.ax_slot_sel
        tool = self._tool_for(iid, local)
        try:
            if self._printer.state in ("printing", "paused"):
                self._screen.show_popup_message("Not while printing.", 2)
                return
        except Exception:
            pass
        self._confirm(f"Test T{tool}?",
                      "The spool feeds to the toolhead sensor and returns to its park position. "
                      "Nothing is loaded into the nozzle.", [],
                      [("Test slot", "ax-green", lambda: (self._send_gcode(f"ACE_CHECK_TOOL TOOL={tool}"),
                                                          self._screen.show_popup_message(f"Testing T{tool}...", 2),
                                                          self._show("home")))])

    def _slot_edit(self):
        iid, local = self.ax_slot_sel
        inv = self.instance_data[iid]["inventory"][local]
        self.ax_edit = {"iid": iid, "local": local, "material": inv.get("material") or "PLA",
                        "temp": inv.get("temp") or self.FILAMENT_TEMP_DEFAULTS.get(inv.get("material") or "PLA", 210),
                        "color": list(inv.get("color") or [255, 255, 255])}
        self.current_config_instance, self.current_config_slot = iid, local
        self._refresh_edit()
        self._show("edit")

    # ------------------------------------------------------------- edit slot
    def _build_edit(self):
        page = self._page()
        self.ax_ed_title = self._lbl("Edit slot", "ax-h1")
        page.pack_start(self.ax_ed_title, False, False, 0)
        page.pack_start(self._hrow(self._btn("Save slot", self._edit_save, "ax-green"),
                                   self._btn("Cancel", lambda: self._show("slot")), homogeneous=True),
                        False, False, 0)
        page.pack_start(self._lbl("Color", "ax-sec"), False, False, 0)
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.ax_ed_dot = Gtk.Box()
        self.ax_ed_dot.get_style_context().add_class("ax-dot")
        self.ax_ed_hex = self._lbl("#FFFFFF", "ax-h2")
        self.ax_pick_btn = self._btn("Hide picker", self._toggle_picker, "ax-small ax-green")
        hdr.pack_start(self.ax_ed_dot, False, False, 0)
        hdr.pack_start(self.ax_ed_hex, True, True, 0)
        hdr.pack_end(self.ax_pick_btn, False, False, 0)
        hdr.pack_end(self._btn("Type hex", self._edit_type_hex, "ax-small ax-blue"), False, False, 0)
        page.pack_start(hdr, False, False, 0)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        for n, rgb in enumerate(SWATCHES):
            d = Gtk.Button()
            d.get_style_context().add_class("ax-sw")
            d.override_background_color(Gtk.StateFlags.NORMAL, rgba(rgb))
            d.connect("clicked", lambda _b, rgb=rgb: self._edit_color(list(rgb)))
            grid.attach(d, n % 6, n // 6, 1, 1)
        page.pack_start(grid, False, False, 0)
        self.ax_picker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ev = Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON1_MOTION_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
        self.ax_sv = Gtk.DrawingArea()
        self.ax_sv.set_size_request(-1, int(240 * self.ax_scale))
        self.ax_sv.add_events(ev)
        self.ax_sv.connect("draw", self._draw_sv)
        self.ax_sv.connect("button-press-event", self._sv_touch)
        self.ax_sv.connect("motion-notify-event", self._sv_touch)
        self.ax_hue = Gtk.DrawingArea()
        self.ax_hue.set_size_request(-1, int(44 * self.ax_scale))
        self.ax_hue.add_events(ev)
        self.ax_hue.connect("draw", self._draw_hue)
        self.ax_hue.connect("button-press-event", self._hue_touch)
        self.ax_hue.connect("motion-notify-event", self._hue_touch)
        self.ax_picker.pack_start(self.ax_sv, False, False, 0)
        self.ax_picker.pack_start(self.ax_hue, False, False, 0)
        page.pack_start(self.ax_picker, False, False, 0)
        page.pack_start(self._lbl("Material", "ax-sec"), False, False, 0)
        grid = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        self.ax_mat_btns = {}
        mats = self.material_options()
        cols = 3 if self._ax_portrait else 5
        for n, m in enumerate(mats):
            b = self._btn(m, lambda m=m: self._edit_material(m))
            grid.attach(b, n % cols, n // cols, 1, 1)
            self.ax_mat_btns[m] = b
        page.pack_start(grid, False, False, 0)

        page.pack_start(self._lbl("Nozzle temperature", "ax-sec"), False, False, 0)
        tr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.ax_ed_temp = self._lbl("210 °C", "ax-h1", 0.5)
        tr.pack_start(self._btn("-", lambda: self._edit_temp(-5)), False, False, 0)
        tr.pack_start(self.ax_ed_temp, True, True, 0)
        tr.pack_start(self._btn("+", lambda: self._edit_temp(5)), False, False, 0)
        page.pack_start(self._card(tr), False, False, 0)

        return page

    def _refresh_edit(self):
        e = self.ax_edit
        if not e:
            return
        self.ax_ed_title.set_text(f"Edit T{self._tool_for(e['iid'], e['local'])}")
        for m, b in self.ax_mat_btns.items():
            sc = b.get_style_context()
            (sc.add_class if m == e["material"] else sc.remove_class)("ax-sel")
        self.ax_ed_temp.set_text(f"{e['temp']} °C")
        self.ax_ed_dot.override_background_color(Gtk.StateFlags.NORMAL, rgba(e["color"]))
        self.ax_ed_hex.set_text(hexcol(e["color"]).upper())
        if not getattr(self, "_ax_picking", False):
            import colorsys
            r, g, b = [c / 255.0 for c in e["color"]]
            h, sat, v = colorsys.rgb_to_hsv(r, g, b)
            if sat > 0.02 and v > 0.02:
                self.ax_hsv = [h, sat, v]
            else:
                self.ax_hsv = [getattr(self, "ax_hsv", [0, 0, 0])[0], sat, v]
            self.ax_sv.queue_draw()
            self.ax_hue.queue_draw()

    def _edit_material(self, m):
        self.ax_edit["material"] = m
        self.ax_edit["temp"] = self.FILAMENT_TEMP_DEFAULTS.get(m, self.ax_edit["temp"])
        self._refresh_edit()

    def _edit_temp(self, d):
        self.ax_edit["temp"] = max(150, min(300, self.ax_edit["temp"] + d))
        self._refresh_edit()

    def _edit_color(self, rgb):
        self.ax_edit["color"] = rgb
        self._refresh_edit()

    def _edit_type_hex(self):
        def done(h):
            rgb = parse_hex(h)
            if rgb is None:
                self._screen.show_popup_message("Not a valid color.", 2)
                return
            self.ax_edit["color"] = rgb
            self._refresh_edit()
            self._show("edit")
        self._numpad("Color (hex)", hexcol(self.ax_edit["color"]).upper(), done, "edit", hexmode=True)

    def _toggle_picker(self):
        vis = not self.ax_picker.get_visible()
        self.ax_picker.set_visible(vis)
        self.ax_pick_btn.set_label("Hide picker" if vis else "Show picker")

    def _hsv_apply(self):
        import colorsys
        h, sat, v = self.ax_hsv
        rgb = [int(round(c * 255)) for c in colorsys.hsv_to_rgb(h, sat, v)]
        self.ax_edit["color"] = rgb
        self._ax_picking = True
        try:
            self._refresh_edit()
        finally:
            self._ax_picking = False
        self.ax_sv.queue_draw()
        self.ax_hue.queue_draw()

    def _sv_touch(self, w, ev):
        W, H = w.get_allocated_width(), w.get_allocated_height()
        self.ax_hsv[1] = max(0.0, min(1.0, ev.x / max(W, 1)))
        self.ax_hsv[2] = 1.0 - max(0.0, min(1.0, ev.y / max(H, 1)))
        self._hsv_apply()
        return True

    def _hue_touch(self, w, ev):
        W = w.get_allocated_width()
        self.ax_hsv[0] = max(0.0, min(0.999, ev.x / max(W, 1)))
        self._hsv_apply()
        return True

    def _draw_sv(self, w, cr):
        import cairo, colorsys
        W, H = w.get_allocated_width(), w.get_allocated_height()
        h, sat, v = getattr(self, "ax_hsv", [0, 0, 1])
        r, g, b = colorsys.hsv_to_rgb(h, 1, 1)
        cr.set_source_rgb(r, g, b)
        cr.rectangle(0, 0, W, H)
        cr.fill()
        gr = cairo.LinearGradient(0, 0, W, 0)
        gr.add_color_stop_rgba(0, 1, 1, 1, 1)
        gr.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(gr)
        cr.rectangle(0, 0, W, H)
        cr.fill()
        gr = cairo.LinearGradient(0, 0, 0, H)
        gr.add_color_stop_rgba(0, 0, 0, 0, 0)
        gr.add_color_stop_rgba(1, 0, 0, 0, 1)
        cr.set_source(gr)
        cr.rectangle(0, 0, W, H)
        cr.fill()
        x, y = sat * W, (1 - v) * H
        cr.new_sub_path()
        cr.arc(x, y, 13, 0, 6.3)
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(4)
        cr.stroke()
        return False

    def _draw_hue(self, w, cr):
        import cairo, colorsys
        W, H = w.get_allocated_width(), w.get_allocated_height()
        gr = cairo.LinearGradient(0, 0, W, 0)
        for i in range(7):
            gr.add_color_stop_rgb(i / 6.0, *colorsys.hsv_to_rgb(i / 6.0 if i < 6 else 0, 1, 1))
        cr.set_source(gr)
        cr.rectangle(0, H * 0.3, W, H * 0.4)
        cr.fill()
        x = getattr(self, "ax_hsv", [0, 0, 1])[0] * W
        cr.new_sub_path()
        cr.arc(x, H / 2, H * 0.42, 0, 6.3)
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.fill()
        return False

    def _edit_save(self):
        e = self.ax_edit
        tool = self._tool_for(e["iid"], e["local"])
        self.config_material, self.config_color, self.config_temp = e["material"], list(e["color"]), e["temp"]
        # stock save: validates, updates the local inventory, sends ACE_SET_SLOT
        base.Panel.save_slot_config(self, None, e["iid"], e["local"], tool)
        self.update_slots_from_data(e["iid"], [dict(s) for s in self.instance_data[e["iid"]]["inventory"]])
        self._show("home")

    # --------------------------------------------------------------- confirm
    def _build_confirm(self):
        page = self._page()
        self.ax_cf_title = self._lbl("", "ax-h1")
        self.ax_cf_sub = self._lbl("", "ax-m", wrap=True)
        self.ax_cf_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ax_cf_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.ax_cf_btns.set_homogeneous(True)
        self.ax_cf_note = self._lbl("", "ax-m", wrap=True)
        page.pack_start(self.ax_cf_title, False, False, 0)
        page.pack_start(self.ax_cf_sub, False, False, 0)
        page.pack_start(self._card(self.ax_cf_rows), False, False, 0)
        page.pack_start(self.ax_cf_btns, False, False, 0)
        page.pack_start(self.ax_cf_note, False, False, 0)
        return page

    def _confirm(self, title, sub, rows, buttons, note="", cancel_to=None):
        self.ax_cf_title.set_text(title)
        self.ax_cf_sub.set_text(sub)
        self.ax_cf_note.set_text(note)
        for c in self.ax_cf_rows.get_children():
            self.ax_cf_rows.remove(c)
        for r in rows:
            k, v = r[0], r[1]
            row = self._kv(k, "")
            lab = row.get_children()[-1]
            lab.set_markup(f'<span foreground="{r[2] if len(r) > 2 else TEXT}">{v}</span>')
            self.ax_cf_rows.pack_start(row, False, False, 0)
        self.ax_cf_rows.get_parent().set_visible(bool(rows))
        for c in self.ax_cf_btns.get_children():
            self.ax_cf_btns.remove(c)
        back = cancel_to or self._ax_prev
        self.ax_cf_btns.pack_start(self._btn("Cancel", lambda: self._show(back)), True, True, 0)
        for label, cls, cb in buttons:
            def run(cb=cb):
                cb()
            self.ax_cf_btns.pack_start(self._btn(label, run, cls), True, True, 0)
        self.ax_cf_rows.show_all()
        self.ax_cf_btns.show_all()
        self._show("confirm")
        self.ax_cf_rows.get_parent().set_visible(bool(rows))

    def show_load_confirmation(self, instance_id, global_tool):
        local = global_tool - self.instance_data[instance_id]["tool_offset"]
        inv = self.instance_data[instance_id]["inventory"][local]
        cur = self.get_current_loaded_slot()
        rows = [("Material", inv.get("material") or "-"), ("Nozzle", f"{inv.get('temp', 0)} °C")]
        if cur != -1:
            rows.append(("Currently loaded", f"T{cur}", AMBER))

        def go():
            self._load_tool(global_tool)
            self._show("home")

        def force():
            self._force_unload(global_tool)
            self._show("home")
        self._confirm(f"Load T{global_tool}?", "The nozzle will heat first." if cur == -1
                      else f"T{cur} is unloaded first.", rows,
                      [("Load", "ax-green", go), ("Force unload", "ax-amber", force)],
                      "Force unload ignores the sensors. Use it only if the sensors are wrong.",
                      cancel_to="slot")

    def _show_unload_dialog(self, instance_id, global_tool, slot_info):
        def sv(v):
            return ("-", MUTED) if v is None else (("filament seen", GREEN) if v else ("clear", AMBER))
        th, rd = sv(self.toolhead_sensor), sv(self.rdm_sensor)
        rows = [("Toolhead sensor", th[0], th[1]), ("RDM sensor", rd[0], rd[1])]
        local = global_tool - self.instance_data[instance_id]["tool_offset"]
        inv = self.instance_data[instance_id]["inventory"][local]
        rows.insert(0, ("Material", f"{inv.get('material') or '-'} {inv.get('temp', 0)} °C"))

        def unl():
            self._send_gcode("UNLOAD_TOOL")
            self._screen.show_popup_message("Unloading...", 1)
            self._show("home")

        def force():
            self._force_unload(global_tool)
            self._show("home")

        def load():
            self._load_tool(global_tool)
            self._show("home")
        if self._sensors_indicate_no_filament():
            self._confirm(f"Inconsistent state: T{global_tool}",
                          "The ACE says this tool is loaded, but a sensor reports no filament. "
                          "The filament may have been removed by hand.", rows,
                          [("Load again", "ax-green", load), ("Unload", "ax-red", unl)],
                          cancel_to="slot")
            return
        self._confirm(f"Unload T{global_tool}?", "The nozzle will heat first.", rows,
                      [("Unload", "ax-red", unl), ("Force unload", "ax-amber", force)],
                      "Force unload ignores the sensors. Use it only if the sensors are wrong.",
                      cancel_to="slot")

    # -------------------------------------------------------------- progress
    def _build_progress(self):
        page = self._page()
        self.ax_pg_title = self._lbl("Tool change", "ax-h1")
        self.ax_pg_sub = self._lbl("", "ax-m")
        self.ax_pg_steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self.ax_pg_title, False, False, 0)
        page.pack_start(self.ax_pg_sub, False, False, 0)
        page.pack_start(self._card(self.ax_pg_steps), False, False, 0)
        page.pack_start(self._btn("Hide", lambda: self._show("home")), False, False, 0)
        return page

    STEP_NAMES = {"heat": "Heat nozzle", "cut": "Cut filament", "retract": "Retract old filament",
                  "load": "Load new filament", "feed": "Feed to the toolhead", "purge": "Purge",
                  "wipe": "Wipe nozzle", "park": "Park old filament", "prime": "Prime nozzle"}

    def _refresh_progress(self):
        st = self.ax_state
        phase = st.get("toolchange_phase", "")
        steps = list(st.get("toolchange_steps") or [])
        tgt = self.target_tool_index
        self.ax_pg_title.set_text(f"Loading T{tgt}" if tgt != -1 else "Tool change")
        self.ax_pg_sub.set_text(f"Step: {self.STEP_NAMES.get(phase, phase) or '...'}")
        for c in self.ax_pg_steps.get_children():
            self.ax_pg_steps.remove(c)
        allsteps = ([phase] if phase and phase not in steps else []) + steps
        for s in allsteps:
            act = s == phase
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.get_style_context().add_class("ax-row")
            r.pack_start(self._lbl(("▶ " if act else "○ ") + self.STEP_NAMES.get(s, s),
                                   "ax-t" if act else "ax-m"), True, True, 0)
            self.ax_pg_steps.pack_start(r, False, False, 0)
        self.ax_pg_steps.show_all()

    # ----------------------------------------------------------------- tools
    def _build_tools(self):
        page = self._page()
        page.pack_start(self._lbl("Utilities", "ax-h1"), False, False, 0)
        page.pack_start(self._lbl("Slot to work on", "ax-sec"), False, False, 0)
        self.ax_tool_box = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        page.pack_start(self.ax_tool_box, False, False, 0)
        self.ax_tool_btns = {}
        for n in range(len(self.ace_instances) * 4):
            b = self._btn(f"T{n}", lambda n=n: self._tools_select(n))
            self.ax_tool_box.attach(b, n % 4, n // 4, 1, 1)
            self.ax_tool_btns[n] = b
        page.pack_start(self._lbl("Move filament", "ax-sec"), False, False, 0)
        self.ax_btn_feed = self._btn("Feed 100 mm", lambda: self._amount_numpad("feed"), "ax-blue")
        self.ax_btn_ret = self._btn("Retract 100 mm", lambda: self._amount_numpad("retract"), "ax-blue")
        page.pack_start(self._hrow(self.ax_btn_feed, self.ax_btn_ret, homogeneous=True), False, False, 0)
        page.pack_start(self._hrow(self._btn("Stop feed", lambda: self.spool_stop_feed(None)),
                                   self._btn("Stop retract", lambda: self.spool_stop_retract(None)),
                                   homogeneous=True), False, False, 0)
        page.pack_start(self._lbl("Feed assist", "ax-sec"), False, False, 0)
        page.pack_start(self._hrow(self._btn("Enable", lambda: self.spool_enable_feed_assist(None)),
                                   self._btn("Disable", lambda: self.spool_disable_feed_assist(None)),
                                   homogeneous=True), False, False, 0)
        page.pack_start(self._lbl("Load and unload", "ax-sec"), False, False, 0)
        page.pack_start(self._hrow(self._btn("Smart load all", lambda: self.spool_smart_load(None), "ax-green"),
                                   self._btn("Smart unload", lambda: self.spool_smart_unload(None), "ax-red"),
                                   self._btn("Full unload", lambda: self._full_unload_confirm(), "ax-amber"),
                                   homogeneous=True), False, False, 0)
        page.pack_start(self._lbl("ACE unit", "ax-sec"), False, False, 0)
        page.pack_start(self._hrow(self._btn("Reconnect", lambda: self.spool_reconnect(None), "ax-blue"),
                                   self._btn("RFID sync on", lambda: self.spool_enable_rfid_sync(None)),
                                   self._btn("RFID sync off", lambda: self.spool_disable_rfid_sync(None)),
                                   homogeneous=True), False, False, 0)
        return page

    def _refresh_tools(self):
        for n, b in self.ax_tool_btns.items():
            sc = b.get_style_context()
            (sc.add_class if n == self.ax_sel_tool else sc.remove_class)("ax-sel")
        self.ax_btn_feed.set_label(f"Feed {self.ax_amount} mm")
        self.ax_btn_ret.set_label(f"Retract {self.ax_amount} mm")

    def _tools_select(self, n):
        self.ax_sel_tool = n
        self.spool_selected_tool = n
        self._refresh_tools()

    def _full_unload_confirm(self):
        tool = self.ax_sel_tool
        self._confirm(f"Full unload T{tool}?",
                      "Pulls the filament all the way back into the ACE.", [],
                      [("Full unload", "ax-amber", lambda: (self._send_gcode(f"ACE_FULL_UNLOAD TOOL={tool}"),
                                                            self._screen.show_popup_message(f"Full unload T{tool}...", 1),
                                                            self._show("tools")))],
                      cancel_to="tools")

    def _spool_selected_tool_or_popup(self):
        return self.ax_sel_tool

    def _spool_selected_tool_optional(self):
        return self.ax_sel_tool

    def _amount_numpad(self, kind):
        def done(val):
            try:
                v = int(round(float(val)))
                if v <= 0:
                    raise ValueError
            except Exception:
                self._screen.show_popup_message("Enter a valid positive amount")
                return
            self.ax_amount = v
            cmd = "ACE_FEED" if kind == "feed" else "ACE_RETRACT"
            self._send_gcode(f"{cmd} T={self.ax_sel_tool} LENGTH={v}")
            self._screen.show_popup_message(
                f"{'Feeding' if kind == 'feed' else 'Retracting'} {v} mm on T{self.ax_sel_tool}", 1)
            self._show("tools")
        self._numpad(f"{'Feed' if kind == 'feed' else 'Retract'} T{self.ax_sel_tool} (mm)",
                     str(self.ax_amount), done, "tools")

    # ---------------------------------------------------------------- numpad
    def _build_numpad(self):
        page = self._page()
        self.ax_np_title = self._lbl("", "ax-h2")
        self.ax_np_val = self._lbl("0", "ax-h1", 0.5)
        page.pack_start(self.ax_np_title, False, False, 0)
        page.pack_start(self._card(self.ax_np_val), False, False, 0)
        g = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "CLR", "0", "<"]
        for n, k in enumerate(keys):
            g.attach(self._btn(k, lambda k=k: self._np_key(k)), n % 3, n // 3, 1, 1)
        self.ax_np_dec = g
        page.pack_start(g, False, False, 0)
        gh = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        hkeys = list("0123456789ABCDEF") + ["CLR", "<"]
        for n, k in enumerate(hkeys):
            gh.attach(self._btn(k, lambda k=k: self._np_key(k)), n % 6, n // 6, 1, 1)
        self.ax_np_hex = gh
        page.pack_start(gh, False, False, 0)
        page.pack_start(self._hrow(self._btn("OK", lambda: self._np_ok(), "ax-green"),
                                   self._btn("Cancel", lambda: self._show(self._np_back)), homogeneous=True),
                        False, False, 0)
        return page

    def _numpad(self, title, initial, cb, back, hexmode=False):
        self._np_hex = hexmode
        self.ax_np_title.set_text(title)
        self._np_buf = ""
        self.ax_np_val.set_text(initial)
        self._np_cb, self._np_back = cb, back
        self._show("numpad")
        self.ax_np_dec.set_visible(not hexmode)
        self.ax_np_hex.set_visible(hexmode)

    def _np_key(self, k):
        if k == "CLR":
            self._np_buf = ""
        elif k == "<":
            self._np_buf = self._np_buf[:-1]
        elif len(self._np_buf) < (6 if getattr(self, "_np_hex", False) else 5):
            self._np_buf += k
        if getattr(self, "_np_hex", False):
            self.ax_np_val.set_text("#" + (self._np_buf or "______"))
        else:
            self.ax_np_val.set_text(self._np_buf or "0")

    def _np_ok(self):
        if getattr(self, "_np_hex", False):
            if len(self._np_buf) != 6:
                self._screen.show_popup_message("Enter 6 characters, 0-9 and A-F.", 2)
                return
            self._np_cb(self._np_buf)
            return
        val = self._np_buf or self.ax_np_val.get_text()
        self._np_cb(val)

    # ---------------------------------------------------------------- dryer
    def _build_dryer(self):
        page = self._page()
        page.pack_start(self._lbl("Dryer", "ax-h1"), False, False, 0)
        self.ax_dr_unit_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.ax_dr_unit_box.set_homogeneous(True)
        self.ax_dr_unit_btns = {}
        for key in ["ALL"] + list(self.ace_instances):
            b = self._btn("All units" if key == "ALL" else f"ACE {key}", lambda k=key: self._dryer_pick(k))
            self.ax_dr_unit_box.pack_start(b, True, True, 0)
            self.ax_dr_unit_btns[key] = b
        if len(self.ace_instances) > 1:
            page.pack_start(self.ax_dr_unit_box, False, False, 0)
        self.ax_dr_status = self._lbl("", "ax-t")
        self.ax_dr_gauge = Gtk.DrawingArea()
        self.ax_dr_gauge.set_size_request(-1, int(180 * self.ax_scale))
        self.ax_dr_gauge.connect("draw", self._draw_gauge)
        page.pack_start(self.ax_dr_status, False, False, 0)
        page.pack_start(self.ax_dr_gauge, False, False, 0)
        page.pack_start(self._lbl("Presets", "ax-sec"), False, False, 0)
        g = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        self.ax_preset_btns = {}
        for n, (name, t, d) in enumerate(PRESETS):
            b = self._btn(f"{name}\n{t}° · {d // 60} h" if t else "Custom\nsliders",
                          lambda name=name, t=t, d=d: self._dryer_preset(name, t, d))
            b.get_child().set_justify(Gtk.Justification.CENTER)
            g.attach(b, n % 3, n // 3, 1, 1)
            self.ax_preset_btns[name] = b
        page.pack_start(g, False, False, 0)
        self.ax_dr_temp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 25, 65, 5)
        self.ax_dr_dur = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 30, 480, 30)
        for sc, name, cb in ((self.ax_dr_temp, "Temperature (°C)", self._dryer_temp_changed),
                             (self.ax_dr_dur, "Duration (min)", self._dryer_dur_changed)):
            sc.set_draw_value(True)
            sc.set_value_pos(Gtk.PositionType.RIGHT)
            sc.connect("value-changed", cb)
            page.pack_start(self._lbl(name, "ax-sec"), False, False, 0)
            page.pack_start(sc, False, False, 0)
        self.ax_dr_temp.set_value(45)
        self.ax_dr_dur.set_value(240)
        page.pack_start(self._hrow(self._btn("Start dryer", self._dryer_start, "ax-amber"),
                                   self._btn("Stop", self._dryer_stop, "ax-blue"), homogeneous=True),
                        False, False, 0)
        return page

    def _dryer_max(self):
        mx = 55.0
        for e in self.ax_extra.values():
            if e.get("max_dryer_temperature"):
                mx = max(mx, float(e["max_dryer_temperature"]))
        return int(min(mx, 65))

    def _dryer_pick(self, k):
        self.ax_dryer_sel = k
        self.selected_dryer_instance = k
        self._refresh_dryer()

    def _dryer_preset(self, name, t, d):
        if t:
            self.ax_dr_temp.set_value(min(t, self._dryer_max()))
            self.ax_dr_dur.set_value(d)
        self._refresh_dryer()

    def _dryer_temp_changed(self, sc):
        self.ax_dryer_temp = int(sc.get_value())

    def _dryer_dur_changed(self, sc):
        self.ax_dryer_dur = int(sc.get_value())

    def _dryer_targets(self):
        return list(self.ace_instances) if self.ax_dryer_sel == "ALL" else [self.ax_dryer_sel]

    def _dryer_start(self):
        t = min(self.ax_dryer_temp, self._dryer_max())
        for iid in self._dryer_targets():
            p = f" INSTANCE={iid}" if iid > 0 else ""
            self._send_gcode(f"ACE_START_DRYING{p} TEMP={t} DURATION={self.ax_dryer_dur}")
        self._screen.show_popup_message(f"Dryer {t}°C for {self.ax_dryer_dur} min", 2)

    def _dryer_stop(self):
        for iid in self._dryer_targets():
            p = f" INSTANCE={iid}" if iid > 0 else ""
            self._send_gcode(f"ACE_STOP_DRYING{p}")
        self._screen.show_popup_message("Stopping dryer", 1)

    def _dryer_info(self):
        iids = self._dryer_targets()
        e = self.ax_extra.get(iids[0], {}) if iids else {}
        ds = e.get("dryer_status") or {}
        return e, ds

    def _refresh_dryer(self):
        for k, b in self.ax_dr_unit_btns.items():
            sc = b.get_style_context()
            (sc.add_class if k == self.ax_dryer_sel else sc.remove_class)("ax-sel")
        e, ds = self._dryer_info()
        st = ds.get("status", "stop")
        if st == "drying":
            rt = int(ds.get("remain_time", 0))
            self.ax_dr_status.set_markup(
                f'<span foreground="{GREEN}">Drying · {rt // 3600}h {(rt % 3600) // 60}m left</span>')
        else:
            self.ax_dr_status.set_markup(f'<span foreground="{MUTED}">Stopped</span>')
        self.ax_dr_gauge.queue_draw()

    def _draw_gauge(self, area, cr):
        w, h = area.get_allocated_width(), area.get_allocated_height()
        e, ds = self._dryer_info()
        cur = float(e.get("temp", 0) or 0)
        tgt = float(ds.get("target_temp", 0) or self.ax_dryer_temp)
        cx, cy, r = w / 2, h / 2, min(w, h) / 2 - 12
        cr.set_line_width(14)
        cr.set_source_rgb(0.15, 0.16, 0.17)
        cr.arc(cx, cy, r, 0.75 * math.pi, 2.25 * math.pi)
        cr.stroke()
        frac = max(0.0, min(1.0, cur / max(tgt, 1)))
        cr.set_source_rgb(0.88, 0.63, 0.19)
        cr.set_line_cap(1)
        cr.arc(cx, cy, r, 0.75 * math.pi, 0.75 * math.pi + 1.5 * math.pi * frac)
        cr.stroke()
        cr.set_source_rgb(0.91, 0.9, 0.88)
        cr.select_font_face("DejaVu Sans", 0, 1)
        cr.set_font_size(38 * self.ax_scale)
        t = f"{cur:.0f}°"
        ex = cr.text_extents(t)
        cr.move_to(cx - ex.width / 2, cy + 8)
        cr.show_text(t)
        cr.set_font_size(15 * self.ax_scale)
        cr.set_source_rgb(0.55, 0.57, 0.59)
        t2 = f"inside the ACE · target {tgt:.0f}°"
        ex = cr.text_extents(t2)
        cr.move_to(cx - ex.width / 2, cy + 32)
        cr.show_text(t2)
        return False

    # --------------------------------------------------------------- status
    def _build_status(self):
        page = self._page()
        page.pack_start(self._lbl("Status", "ax-h1"), False, False, 0)
        self.ax_st_conn = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ax_st_sens = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ax_st_stats = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self._lbl("ACE units", "ax-sec"), False, False, 0)
        page.pack_start(self._card(self.ax_st_conn), False, False, 0)
        page.pack_start(self._lbl("Sensors", "ax-sec"), False, False, 0)
        page.pack_start(self._card(self.ax_st_sens), False, False, 0)
        page.pack_start(self._btn("Fix the filament position", lambda: self._show("position"), "ax-blue"),
                        False, False, 0)
        page.pack_start(self._lbl("Usage", "ax-sec"), False, False, 0)
        page.pack_start(self._card(self.ax_st_stats), False, False, 0)
        self.ax_st_reset = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.ax_st_reset.set_homogeneous(True)
        for what, label in (("cuts", "Reset cuts"), ("tool_changes", "Reset changes"), ("purge_mm", "Reset purge")):
            self.ax_st_reset.pack_start(self._btn(label, lambda w=what, l=label: self._reset_stat(w, l)),
                                        True, True, 0)
        page.pack_start(self.ax_st_reset, False, False, 0)
        return page

    def _reset_stat(self, what, label):
        self._confirm(f"{label}?", "The counter goes back to 0.", [],
                      [("Reset", "ax-amber", lambda: (self._send_gcode(f"ACE_RESET_STATS WHAT={what}"),
                                                      self._show("status")))], cancel_to="status")

    def _clear(self, box):
        for c in box.get_children():
            box.remove(c)

    def _refresh_status(self):
        self._clear(self.ax_st_conn)
        for iid in self.ace_instances:
            e = self.ax_extra.get(iid, {})
            st = self.instance_data[iid].get("connection_state") or "unknown"
            good = st == "connected"
            self.ax_st_conn.pack_start(self._kv(
                f"ACE {iid}", ""), False, False, 0)
            row = self.ax_st_conn.get_children()[-1]
            row.get_children()[-1].set_markup(
                f'<span foreground="{GREEN if good else AMBER}">{st}</span>')
            detail = " · ".join(str(x) for x in (e.get("model"), e.get("firmware"), e.get("usb_port")) if x)
            if detail:
                self.ax_st_conn.pack_start(self._lbl(detail, "ax-m"), False, False, 0)
        self._clear(self.ax_st_sens)

        def sv(v):
            return ("not fitted", MUTED) if v is None else (("filament seen", GREEN) if v else ("clear", MUTED))
        for name, v in (("Toolhead sensor", self.toolhead_sensor), ("RDM sensor", self.rdm_sensor)):
            row = self._kv(name, "")
            t, c = sv(v)
            row.get_children()[-1].set_markup(f'<span foreground="{c}">{t}</span>')
            self.ax_st_sens.pack_start(row, False, False, 0)
        pos = self.ax_saved.get("ace_filament_pos", "unknown")
        self.ax_st_sens.pack_start(self._kv("Saved position", str(pos)), False, False, 0)
        self._clear(self.ax_st_stats)
        stats = self.ax_state.get("stats") or {}
        cuts = int(stats.get("cuts", 0))
        self.ax_st_stats.pack_start(self._kv("Tool changes", str(stats.get("tool_changes", 0))), False, False, 0)
        self.ax_st_stats.pack_start(self._kv("Purged", f"{float(stats.get('purge_mm', 0)) / 1000:.2f} m"),
                                    False, False, 0)
        row = self._kv("Cuts (blade life)", f"{cuts} of {BLADE_LIFE_CUTS}")
        self.ax_st_stats.pack_start(row, False, False, 0)
        if cuts >= BLADE_LIFE_CUTS * 0.9:
            self.ax_st_stats.pack_start(self._lbl("Check or replace the cutter blade soon.", "ax-warn"),
                                        False, False, 0)
        pb = Gtk.ProgressBar()
        pb.set_fraction(min(1.0, cuts / BLADE_LIFE_CUTS))
        self.ax_st_stats.pack_start(pb, False, False, 4)
        for b in (self.ax_st_conn, self.ax_st_sens, self.ax_st_stats):
            b.show_all()

    # ---------------------------------------------------------------- check
    def _build_check(self):
        page = self._page()
        page.pack_start(self._lbl("Check the print", "ax-h1"), False, False, 0)
        page.pack_start(self._lbl("Compare a file's colors with the loaded spools.", "ax-m", wrap=True),
                        False, False, 0)
        page.pack_start(self._lbl("File", "ax-sec"), False, False, 0)
        self.ax_ck_files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.pack_start(self.ax_ck_files, False, False, 0)
        self.ax_ck_title = self._lbl("", "ax-h2", wrap=True)
        self.ax_ck_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ax_ck_msg = self._lbl("", "ax-m", wrap=True)
        page.pack_start(self.ax_ck_title, False, False, 0)
        self.ax_ck_card = self._card(self.ax_ck_rows)
        page.pack_start(self.ax_ck_card, False, False, 0)
        page.pack_start(self.ax_ck_msg, False, False, 0)
        self.ax_ck_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.ax_ck_btns.set_homogeneous(True)
        page.pack_start(self.ax_ck_btns, False, False, 0)
        return page

    def _http(self, path, cb):
        def work():
            try:
                with urllib.request.urlopen(MOONRAKER + path, timeout=8) as r:
                    data = json.loads(r.read().decode())
            except Exception as e:
                logging.debug(f"ACE: http {path} failed: {e}")
                data = None
            GLib.idle_add(cb, data)
        threading.Thread(target=work, daemon=True).start()

    def _check_refresh_files(self):
        def got(data):
            self._clear(self.ax_ck_files)
            files = []
            try:
                files = sorted(data["result"], key=lambda f: f.get("modified", 0), reverse=True)[:5]
            except Exception:
                pass
            cur = None
            try:
                cur = self._printer.get_stat("print_stats", "filename")
            except Exception:
                pass
            names = ([cur] if cur else []) + [f["path"] for f in files if f.get("path") != cur]
            for nm in names[:5]:
                b = self._btn(("Printing: " if nm == cur else "") + nm,
                              lambda nm=nm: self._check_file(nm))
                b.get_child().set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                self.ax_ck_files.pack_start(b, False, False, 0)
            if not names:
                self.ax_ck_files.pack_start(self._lbl("No G-code files found.", "ax-m"), False, False, 0)
            self.ax_ck_files.show_all()
        self._http("/server/files/list?root=gcodes", got)

    @staticmethod
    def _split(v):
        clean = lambda x: str(x).strip().strip("[]\"' ")
        if isinstance(v, list):
            return [clean(x) for x in v]
        if isinstance(v, str):
            return [clean(x) for x in v.replace(",", ";").split(";") if clean(x)]
        return []

    def _check_file(self, name):
        self.ax_ck_name = name

        def got(data):
            try:
                m = data["result"]
            except Exception:
                self.ax_ck_msg.set_text("Could not read the file's details.")
                return
            types = self._split(m.get("filament_type"))
            cols = self._split(m.get("filament_colors") or m.get("filament_colour"))
            tools = m.get("referenced_tools") or list(range(max(len(types), len(cols), 1)))
            req = {}
            for t in tools:
                t = int(t)
                req[t] = (types[t] if t < len(types) else "",
                          parse_hex(cols[t]) if t < len(cols) else None)
            self.ax_check = {"file": name, "req": req, "map": {}}
            self._render_check()
        self._http("/server/files/metadata?filename=" + urllib.parse.quote(name), got)

    def _slot_for_tool(self, tool):
        iid, local = self._loc_for_tool(tool)
        if iid is None:
            return None
        return self.instance_data[iid]["inventory"][local]

    @staticmethod
    def _cdist(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

    def _tool_match(self, req, slot):
        if not slot or slot.get("status") != "ready":
            return False
        mat, col = req
        if mat and (slot.get("material") or "").upper() != mat.upper():
            return False
        if col and slot.get("color") and self._cdist(col, slot["color"]) > 90:
            return False
        return True

    def _render_check(self):
        ck = self.ax_check
        self.ax_ck_title.set_text(ck["file"])
        self._clear(self.ax_ck_rows)
        problems = 0
        total = len(self.ace_instances) * 4
        for tool, req in sorted(ck["req"].items()):
            src = ck["map"].get(tool, tool)
            slot = self._slot_for_tool(src)
            ok = self._tool_match(req, slot)
            if not ok:
                problems += 1
            mat, col = req
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.get_style_context().add_class("ax-row")
            d = Gtk.Box()
            d.get_style_context().add_class("ax-dot")
            d.override_background_color(Gtk.StateFlags.NORMAL, rgba(col or [90, 90, 90]))
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            v.pack_start(self._lbl(f"Print T{tool} needs {mat or 'any'}{' ' + hexcol(col) if col else ''}",
                                   "ax-t"), False, False, 0)
            if slot and slot.get("status") == "ready":
                sub = f"Slot T{src} has {slot.get('material') or '-'} {hexcol(slot.get('color') or [0, 0, 0])}"
            else:
                sub = f"Slot T{src} is empty"
            v.pack_start(self._lbl(sub, "ax-ok" if ok else "ax-warn"), False, False, 0)
            r.pack_start(d, False, False, 0)
            r.pack_start(v, True, True, 0)
            b = self._btn("OK" if ok else "Swap", None, "")
            if not ok:
                b.connect("clicked", lambda _b, t=tool: self._check_swap(t))
            else:
                b.set_sensitive(False)
            r.pack_end(b, False, False, 0)
            self.ax_ck_rows.pack_start(r, False, False, 0)
        self.ax_ck_msg.set_text("Every tool has a matching spool." if not problems
                                else f"{problems} tool(s) do not match. Tap Swap to choose another slot.")
        self._clear(self.ax_ck_btns)
        if ck["map"]:
            self.ax_ck_btns.pack_start(self._btn("Apply swap", self._check_apply, "ax-amber"), True, True, 0)
        self.ax_ck_btns.pack_start(self._btn("Clear tool map",
                                             lambda: (self._send_gcode("ACE_CLEAR_TOOL_MAP"),
                                                      self._screen.show_popup_message("Tool map cleared", 1))),
                                   True, True, 0)
        self.ax_ck_rows.show_all()
        self.ax_ck_btns.show_all()
        self.ax_ck_card.set_visible(True)

    def _check_swap(self, tool):
        ck = self.ax_check
        req = ck["req"][tool]
        used = set(ck["map"].get(t, t) for t in ck["req"] if t != tool)
        cands = [t for t in range(len(self.ace_instances) * 4)
                 if t not in used and self._tool_match(req, self._slot_for_tool(t))]
        if not cands:
            self._screen.show_popup_message("No ready spool matches this tool.", 2)
            return
        cur = ck["map"].get(tool, tool)
        nxt = cands[(cands.index(cur) + 1) % len(cands)] if cur in cands else cands[0]
        ck["map"][tool] = nxt
        self._render_check()

    def _check_apply(self):
        ck = self.ax_check
        m = ",".join(f"{a}:{b}" for a, b in sorted(ck["map"].items()))
        self._send_gcode(f'ACE_SET_TOOL_MAP MAP={m} FILE="{ck["file"]}"')
        self._screen.show_popup_message(f"Tool map set: {m}", 2)

    # -------------------------------------------------------------- settings
    def _build_settings(self):
        page = self._page()
        page.pack_start(self._lbl("Settings", "ax-h1"), False, False, 0)
        self.ax_settings_dep = []
        page.pack_start(self._lbl("During a print", "ax-sec"), False, False, 0)
        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.endless_spool_switch = Gtk.Switch()
        self.endless_spool_status = Gtk.Label()
        self.endless_spool_switch.connect("notify::active", self.on_endless_spool_toggled)
        self.endless_spool_control = self._switch_row(
            "Endless spool", "When a spool runs out, keep printing from another slot.", self.endless_spool_switch)
        c.pack_start(self.endless_spool_control, False, False, 0)
        self.ax_match_btns = {}
        mr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        mr.set_homogeneous(True)
        for k, t in (("exact", "Exact"), ("material", "Material"), ("next", "Next")):
            b = self._btn(t, lambda k=k: self.on_match_mode_selected(k))
            mr.pack_start(b, True, True, 0)
            self.ax_match_btns[k] = b
        c.pack_start(mr, False, False, 6)
        self.ax_chain_btn = self._btn("Takeover order...", lambda: self._show("chain"), "ax-blue")
        c.pack_start(self.ax_chain_btn, False, False, 0)
        page.pack_start(self._card(c), False, False, 0)
        self.ax_settings_dep += [self.endless_spool_control, mr, self.ax_chain_btn]

        page.pack_start(self._lbl("The ACE", "ax-sec"), False, False, 0)
        c2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ace_pro_switch = Gtk.Switch()
        self.ace_pro_status = Gtk.Label()
        self.ace_pro_switch.connect("notify::active", self.on_ace_pro_toggled)
        self.ace_pro_control = self._switch_row(
            "ACE Pro driver", "Turn off to run the printer without the ACE.", self.ace_pro_switch)
        c2.pack_start(self.ace_pro_control, False, False, 0)
        rf = self._hrow(self._btn("Read RFID: on", lambda: self.spool_enable_rfid_sync(None)),
                        self._btn("Read RFID: off", lambda: self.spool_disable_rfid_sync(None)), homogeneous=True)
        tg = self._hrow(self._btn("Tangle detection on", lambda: self._tangle(1)),
                        self._btn("Tangle detection off", lambda: self._tangle(0)), homogeneous=True)
        c2.pack_start(rf, False, False, 4)
        c2.pack_start(tg, False, False, 4)
        page.pack_start(self._card(c2), False, False, 0)
        self.ax_settings_dep += [rf, tg]

        page.pack_start(self._lbl("Speeds and purge", "ax-sec"), False, False, 0)
        sp = self._btn("Feed, retract and purge...", lambda: self._show("speeds"), "ax-blue")
        page.pack_start(sp, False, False, 0)
        self.ax_fw_btn = self._btn("ACE2 firmware update...", lambda: self._show("firmware"), "ax-blue")
        page.pack_start(self.ax_fw_btn, False, False, 0)
        page.pack_start(self._lbl("Maintenance", "ax-sec"), False, False, 0)
        page.pack_start(self._btn("Reset slot inventory...", self._inv_reset_confirm, "ax-amber"), False, False, 0)
        self.ax_settings_dep += [sp, self.ax_fw_btn]
        return page

    def _refresh_settings(self):
        # firmware only matters for ACE2 boxes
        ace2 = any(str(self.ax_extra.get(i, {}).get("protocol", "")).lower() not in ("", "ace1_json")
                   for i in self.ace_instances)
        self.ax_fw_btn.set_visible(ace2)
        self._set_match_mode_ui(getattr(self, "ax_match_mode", "exact"))
        self._update_match_mode_sensitivity()

    def _tangle(self, v):
        self._send_gcode(f"ACE_TANGLE_DETECTION ENABLE={v}")
        self._screen.show_popup_message("Tangle detection " + ("on" if v else "off"), 1)

    def _inv_reset_confirm(self):
        iid = self.current_instance
        self._confirm(f"Reset ACE {iid} inventory?",
                      "Every slot of this unit is marked empty until the ACE reports its spools again.",
                      [], [("Reset", "ax-amber", lambda: (
                          self._send_gcode(f"ACE_RESET_PERSISTENT_INVENTORY INSTANCE={iid}"),
                          self._screen.show_popup_message("Inventory reset", 2), self._show("settings")))],
                      cancel_to="settings")

    # ----------------------------------------------------------------- chain
    def _build_chain(self):
        page = self._page()
        page.pack_start(self._lbl("Endless spool takeover order", "ax-h1"), False, False, 0)
        page.pack_start(self._lbl("When this tool runs out, these slots take over, in the order you tap. "
                                  "If none is ready, the match mode applies.", "ax-m", wrap=True), False, False, 0)
        page.pack_start(self._lbl("Tool that runs out", "ax-sec"), False, False, 0)
        self.ax_ch_tools = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        self.ax_ch_tbtns, self.ax_ch_nbtns = {}, {}
        n = len(self.ace_instances) * 4
        for t in range(n):
            b = self._btn(f"T{t}", lambda t=t: self._chain_pick_tool(t))
            self.ax_ch_tools.attach(b, t % 4, t // 4, 1, 1)
            self.ax_ch_tbtns[t] = b
        page.pack_start(self.ax_ch_tools, False, False, 0)
        page.pack_start(self._lbl("Takes over, in order", "ax-sec"), False, False, 0)
        self.ax_ch_next = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        for t in range(n):
            b = self._btn(f"T{t}", lambda t=t: self._chain_toggle(t))
            self.ax_ch_next.attach(b, t % 4, t // 4, 1, 1)
            self.ax_ch_nbtns[t] = b
        page.pack_start(self.ax_ch_next, False, False, 0)
        self.ax_ch_sum = self._lbl("", "ax-t", wrap=True)
        page.pack_start(self.ax_ch_sum, False, False, 0)
        page.pack_start(self._hrow(self._btn("Save order", self._chain_save, "ax-green"),
                                   self._btn("Remove order", self._chain_remove, "ax-amber"),
                                   homogeneous=True), False, False, 0)
        page.pack_start(self._btn("Remove all orders",
                                  lambda: (self._send_gcode("ACE_CLEAR_ENDLESS_CHAIN"),
                                           self._screen.show_popup_message("All orders removed", 1))),
                        False, False, 0)
        return page

    def _chain_current(self, tool):
        ch = self.ax_state.get("endless_chain") or {}
        v = ch.get(str(tool), ch.get(tool, []))
        return [int(x) for x in v] if isinstance(v, (list, tuple)) else []

    def _chain_pick_tool(self, t):
        self.ax_chain_tool = t
        self.ax_chain_pick = self._chain_current(t)
        self._refresh_chain()

    def _chain_toggle(self, t):
        if t == self.ax_chain_tool:
            return
        if t in self.ax_chain_pick:
            self.ax_chain_pick.remove(t)
        else:
            self.ax_chain_pick.append(t)
        self._refresh_chain()

    def _refresh_chain(self):
        for t, b in self.ax_ch_tbtns.items():
            sc = b.get_style_context()
            (sc.add_class if t == self.ax_chain_tool else sc.remove_class)("ax-sel")
        for t, b in self.ax_ch_nbtns.items():
            sc = b.get_style_context()
            if t in self.ax_chain_pick:
                sc.add_class("ax-sel")
                b.set_label(f"T{t} ({self.ax_chain_pick.index(t) + 1})")
            else:
                sc.remove_class("ax-sel")
                b.set_label(f"T{t}")
            b.set_sensitive(t != self.ax_chain_tool)
        self.ax_ch_sum.set_text(f"T{self.ax_chain_tool} → " + (", ".join(f"T{t}" for t in self.ax_chain_pick)
                                                              if self.ax_chain_pick else "(match mode applies)"))

    def _chain_save(self):
        nxt = ",".join(str(t) for t in self.ax_chain_pick)
        self._send_gcode(f"ACE_SET_ENDLESS_CHAIN TOOL={self.ax_chain_tool} NEXT={nxt}")
        self._screen.show_popup_message("Order saved", 1)

    def _chain_remove(self):
        self.ax_chain_pick = []
        self._send_gcode(f"ACE_SET_ENDLESS_CHAIN TOOL={self.ax_chain_tool} NEXT=")
        self._screen.show_popup_message("Order removed", 1)
        self._refresh_chain()

    # ---------------------------------------------------------------- speeds
    def _build_speeds(self):
        page = self._page()
        page.pack_start(self._lbl("Feed, retract and purge", "ax-h1"), False, False, 0)
        page.pack_start(self._lbl("Slot", "ax-sec"), False, False, 0)
        self.ax_sp_tool = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        self.ax_sp_btns = {}
        for t in range(len(self.ace_instances) * 4):
            b = self._btn(f"T{t}", lambda t=t: self._tools_select(t) or self._refresh_speeds())
            self.ax_sp_tool.attach(b, t % 4, t // 4, 1, 1)
            self.ax_sp_btns[t] = b
        page.pack_start(self.ax_sp_tool, False, False, 0)
        self.ax_sp_val = {}
        for key, title, step, lo, hi, unit in (
                ("feed", "Feed speed", 5, 10, 200, "mm/s"), ("retract", "Retract speed", 5, 10, 200, "mm/s")):
            page.pack_start(self._stepper(key, title, step, lo, hi, unit), False, False, 0)
        page.pack_start(self._hrow(self._btn("Set feed speed", lambda: self._speed_send("feed"), "ax-green"),
                                   self._btn("Set retract speed", lambda: self._speed_send("retract"), "ax-green"),
                                   homogeneous=True), False, False, 0)
        for key, title, step, lo, hi, unit in (("plen", "Purge length", 5, 0, 300, "mm"),
                                               ("pspeed", "Purge speed", 50, 50, 1500, "mm/min")):
            page.pack_start(self._stepper(key, title, step, lo, hi, unit), False, False, 0)
        page.pack_start(self._btn("Set purge", self._purge_send, "ax-green"), False, False, 0)
        page.pack_start(self._lbl("Values start from the driver defaults; nothing changes until you tap Set.",
                                  "ax-m", wrap=True), False, False, 0)
        return page

    def _stepper(self, key, title, step, lo, hi, unit):
        r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        val = self._lbl("", "ax-h2", 0.5)
        self.ax_sp_val[key] = (val, unit)
        r.pack_start(self._lbl(title, "ax-t"), True, True, 0)
        r.pack_start(self._btn("-", lambda: self._step(key, -step, lo, hi)), False, False, 0)
        r.pack_start(val, False, False, 0)
        val.set_size_request(int(120 * self.ax_scale), -1)
        r.pack_start(self._btn("+", lambda: self._step(key, step, lo, hi)), False, False, 0)
        return self._card(r)

    def _step(self, key, d, lo, hi):
        self.ax_speed[key] = max(lo, min(hi, self.ax_speed[key] + d))
        self._refresh_speeds()

    def _refresh_speeds(self):
        for t, b in self.ax_sp_btns.items():
            sc = b.get_style_context()
            (sc.add_class if t == self.ax_sel_tool else sc.remove_class)("ax-sel")
        for k, (lab, unit) in self.ax_sp_val.items():
            lab.set_text(f"{self.ax_speed[k]} {unit}")

    def _speed_send(self, kind):
        cmd = "ACE_SET_FEED_SPEED" if kind == "feed" else "ACE_SET_RETRACT_SPEED"
        self._send_gcode(f"{cmd} T={self.ax_sel_tool} SPEED={self.ax_speed[kind]}")
        self._screen.show_popup_message(f"T{self.ax_sel_tool}: {kind} speed {self.ax_speed[kind]}", 2)

    def _purge_send(self):
        self._send_gcode(f"ACE_SET_PURGE_AMOUNT PURGELENGTH={self.ax_speed['plen']} "
                         f"PURGESPEED={self.ax_speed['pspeed']}")
        self._screen.show_popup_message("Purge amount set", 2)

    # -------------------------------------------------------------- position
    def _build_position(self):
        page = self._page()
        page.pack_start(self._lbl("Where is the filament?", "ax-h1"), False, False, 0)
        page.pack_start(self._lbl("The printer lost track of it. Tell it, or let it check the sensors.",
                                  "ax-m", wrap=True), False, False, 0)
        self.ax_pos_btns = {}
        for key, title, sub in FIL_STATES:
            b = Gtk.Button()
            b.get_style_context().add_class("ax-btn")
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            v.pack_start(self._lbl(title, "ax-t"), False, False, 0)
            v.pack_start(self._lbl(sub, "ax-m", wrap=True), False, False, 0)
            b.add(v)
            b.connect("clicked", lambda _b, k=key: self._pos_pick(k))
            page.pack_start(b, False, False, 0)
            self.ax_pos_btns[key] = b
        self.ax_pos_sens = self._lbl("", "ax-m", wrap=True)
        page.pack_start(self.ax_pos_sens, False, False, 0)
        page.pack_start(self._hrow(self._btn("Apply", self._pos_apply, "ax-amber"),
                                   self._btn("Use the sensors", self._pos_sensors, "ax-blue"),
                                   homogeneous=True), False, False, 0)
        page.pack_start(self._btn("Unload everything", self._pos_unload, "ax-red"), False, False, 0)
        return page

    def _refresh_position(self):
        for k, b in self.ax_pos_btns.items():
            sc = b.get_style_context()
            (sc.add_class if k == self.ax_fil_state else sc.remove_class)("ax-sel")
        self.ax_pos_sens.set_text(
            f"Sensors now: toolhead {'seen' if self.toolhead_sensor else 'clear'}, "
            f"RDM {'seen' if self.rdm_sensor else 'clear'}. "
            f"Saved position: {self.ax_saved.get('ace_filament_pos', 'unknown')}. "
            "Setting the position does not move filament.")

    def _pos_pick(self, k):
        self.ax_fil_state = k
        self._refresh_position()

    def _printing(self):
        try:
            return self._printer.state in ("printing", "paused")
        except Exception:
            return False

    def _pos_apply(self):
        if self._printing():
            self._screen.show_popup_message("Not while printing.", 2)
            return
        self._send_gcode(f"ACE_DEBUG_SET_FILAMENT_STATE STATE={self.ax_fil_state}")
        self._screen.show_popup_message(f"Position set: {self.ax_fil_state}", 2)

    def _pos_sensors(self):
        if self.toolhead_sensor:
            self.ax_fil_state = "toolhead"
        elif self.rdm_sensor:
            self.ax_fil_state = "splitter"
        else:
            self.ax_fil_state = "bowden"
        self._refresh_position()
        self._pos_apply()

    def _pos_unload(self):
        if self._printing():
            self._screen.show_popup_message("Not while printing.", 2)
            return
        self._confirm("Unload everything?", "Pulls whatever is in the path back to the ACE.", [],
                      [("Unload", "ax-red", lambda: (self._send_gcode("ACE_SMART_UNLOAD"),
                                                     self._screen.show_popup_message("Unloading...", 2),
                                                     self._show("status")))], cancel_to="position")

    # -------------------------------------------------------------- firmware
    def _build_firmware(self):
        page = self._page()
        page.pack_start(self._lbl("ACE2 firmware update", "ax-h1"), False, False, 0)
        page.pack_start(self._lbl("Choose the firmware file in your config folder. "
                                  "Do not turn the printer off while it flashes.", "ax-m", wrap=True),
                        False, False, 0)
        self.ax_fw_files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.pack_start(self.ax_fw_files, False, False, 0)
        return page

    def _refresh_firmware(self):
        def got(data):
            self._clear(self.ax_fw_files)
            names = []
            try:
                names = [f["path"] for f in data["result"] if f["path"].lower().endswith(".bin")]
            except Exception:
                pass
            for nm in names:
                self.ax_fw_files.pack_start(self._btn(nm, lambda nm=nm: self._fw_confirm(nm)), False, False, 0)
            if not names:
                self.ax_fw_files.pack_start(self._lbl("No .bin files found.", "ax-m"), False, False, 0)
            self.ax_fw_files.show_all()
        self._http("/server/files/list?root=config", got)

    def _fw_confirm(self, nm):
        if self._printing():
            self._screen.show_popup_message("Not while printing.", 2)
            return
        iid = self.current_instance
        self._confirm(f"Flash ACE {iid}?", nm, [],
                      [("Flash", "ax-red", lambda: (
                          self._send_gcode(f"ACE_FIRMWARE_UPDATE INSTANCE={iid} FILE={nm}"),
                          self._screen.show_popup_message("Flashing...", 3), self._show("status")))],
                      "Do not turn the printer off while it flashes.", cancel_to="firmware")

    # ---------------------------------------------------------- extra polling
    def _ax_start_poll(self):
        if self.ax_poll_id is None:
            self.ax_poll_id = GLib.timeout_add_seconds(3, self._ax_poll)
            GLib.timeout_add(500, lambda: (self._ax_poll(), False)[1])

    def _ax_poll(self):
        try:
            if self._printer.state != "ready":
                return True
            now = time.monotonic()
            if now - getattr(self, "_ax_sent", 0) < 2.5:
                return True            # never stack requests
            self._ax_sent = now
            ws = getattr(self._screen, "_ws", None)
            if not callable(getattr(ws, "send_method", None)):
                return True
            objs = {"ace_state": ["endless_chain", "stats", "toolchange_in_progress",
                                  "toolchange_phase", "toolchange_steps", "tool_map", "tool_map_active"],
                    "save_variables": ["variables"]}
            for iid in self.ace_instances:
                objs[f"ace_instance_{iid}"] = ["dryer_status", "temp", "feed_assist_slot", "model", "firmware",
                                               "usb_port", "protocol", "max_dryer_temperature", "connection_state"]

            def cb(resp, *_):
                try:
                    st = (resp or {}).get("result", {}).get("status", {})
                    self._ax_apply(st)
                except Exception:
                    logging.debug("ACE: ax poll apply failed", exc_info=True)
            ws.send_method("printer.objects.query", {"objects": objs}, cb)
        except Exception:
            logging.debug("ACE: ax poll failed", exc_info=True)
        return True

    def _ax_apply(self, st):
        a = st.get("ace_state") or {}
        self.ax_state.update(a)
        sv = (st.get("save_variables") or {}).get("variables") or {}
        self.ax_saved.update(sv)
        for iid in self.ace_instances:
            d = st.get(f"ace_instance_{iid}")
            if isinstance(d, dict):
                self.ax_extra.setdefault(iid, {}).update(d)
                if d.get("connection_state"):
                    self.instance_data[iid]["connection_state"] = str(d["connection_state"])
        self._update_connection_status_label()
        self._ax_update_pills()
        tc = bool(a.get("toolchange_in_progress"))
        if tc and not self.ax_tc_active and self._ax_page in ("home", "slot", "confirm"):
            self.ax_tc_active = True
            self._show("progress")
        elif tc:
            self.ax_tc_active = True
        elif self.ax_tc_active:
            self.ax_tc_active = False
            if self._ax_page == "progress":
                self._show("home")
        if self._ax_page == "progress":
            self._refresh_progress()
        elif self._ax_page == "dryer":
            self._refresh_dryer()
        elif self._ax_page == "status":
            self._refresh_status()
        elif self._ax_page == "chain" and not self.ax_chain_pick:
            self.ax_chain_pick = self._chain_current(self.ax_chain_tool)
            self._refresh_chain()
        elif self._ax_page == "position":
            self._refresh_position()
        elif self._ax_page == "slot":
            self._refresh_slot_sheet()
