from employee.access import can_edit_hr, can_use_hr


def hr_access(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"hr_can_edit": False, "hr_can_view": False}
    return {
        "hr_can_edit": can_edit_hr(user),
        "hr_can_view": can_use_hr(user),
    }
