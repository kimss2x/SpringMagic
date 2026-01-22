import bpy

class SpringMagicPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    update_url: bpy.props.StringProperty(
        name="Update URL",
        description="URL to a JSON {\"version\": \"1.2.3\"} or plain version string",
        default="https://api.github.com/repos/kimss2x/SpringMagic/tags",
        options={'HIDDEN'}
    )
    last_update_status: bpy.props.StringProperty(
        name="Last Update Status",
        default="",
        options={'HIDDEN'}
    )
    last_update_version: bpy.props.StringProperty(
        name="Last Update Version",
        default="",
        options={'HIDDEN'}
    )
    last_checked: bpy.props.StringProperty(
        name="Last Checked",
        default="",
        options={'HIDDEN'}
    )

    def draw(self, context):
        layout = self.layout

        # Version Info Section
        box = layout.box()
        box.label(text="Version Info", icon="INFO")

        # Get current addon version
        addon = context.preferences.addons.get(__package__)
        version = None
        if addon and hasattr(addon, "module") and hasattr(addon.module, "bl_info"):
            version = addon.module.bl_info.get("version", None)

        col = box.column(align=True)
        if version:
            version_str = ".".join(str(v) for v in version)
            col.label(text=f"Current Version: {version_str}")
        else:
            col.label(text="Current Version: Unknown")
        col.label(text=f"Blender: {bpy.app.version_string}")

        # Update Check Section
        box = layout.box()
        box.label(text="Update Check", icon="FILE_REFRESH")

        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("sj_phaser.check_update", text="Check for Updates", icon="URL")

        # Status display
        if self.last_update_status:
            status_box = box.box()
            # Color based on status
            if "Update available" in self.last_update_status:
                status_box.alert = True
            status_box.label(text=self.last_update_status, icon="CHECKMARK" if "Up to date" in self.last_update_status else "ERROR" if "Update available" in self.last_update_status else "INFO")

        if self.last_checked:
            box.label(text=f"Last checked: {self.last_checked}", icon="TIME")
