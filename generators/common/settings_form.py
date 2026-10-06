import os

def get_standard_settings_form():
    with open(os.path.dirname(__file__) + '/settings_form.html', 'r') as reader:
        return reader.read()    


def make_ids_unique(form):
    """Give every field an id that starts with the form's own name ("classicbin_sizeUnitsX").

       All the generators' forms are on one page and several have fields of the same name, so
       the ids were repeated (sizeUnitsX five times): a label then focuses the first form's
       field whichever form it is in. The field NAMES are untouched, and so are the values
       posted; the scripts read fields by name."""
    for field in form:
        field.id = f"{form.id}_{field.name}"
        if field.label is not None:
            field.label.field_id = field.id
    return form
