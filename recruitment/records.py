from recruitment.models import Application


def hired_from(employee):
    return (
        Application.objects.filter(employee=employee)
        .select_related("vacancy", "vacancy__company", "vacancy__designation")
        .first()
    )
