# PiSelfhosting: Data Contracts

**Version:** 1.0
**Status:** Active

This document is the Single Source of Truth (SST) for the schema of all
core data files used within the PiSelfhosting project. It serves as a
formal specification to ensure that the **configurator_app**, the
**editor_app**, and all manager classes operate on a consistent and
well-defined data structure.

All data files must adhere to the schemas defined herein.

---

## `template-config/variables.json`

This file defines the user-configurable variables for a component. It is an
array of variable objects, where each object has the following properties:

| Property      | Type     | Required | Description                                                                                                                                                                                                                                                                                                                               |
|---------------|----------|----------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`          | `string` | Yes      | The unique identifier for the variable. This is used as the key in the `.env` file and for template substitution (e.g., `{{ MY_VARIABLE_ID }}`). By convention, this should be uppercase.                                                                                                                                                   |
| `label`       | `string` | No       | A short, human-readable name for the UI. If not provided, the UI will derive a title from the `id`.                                                                                                                                                                                                                                       |
| `description` | `string` | Yes      | A detailed, user-facing explanation of what the variable is for, including any security implications, required formats, or default behaviors. This is a critical field for ensuring correct configuration.                                                                                                                             |
| `type`        | `string` | Yes      | The data type of the input, which controls the UI rendering. Valid options are: `text`, `password`.                                                                                                                                                                                                                                     |
| `default`     | `string` | No       | The default value to pre-populate in the UI input field.                                                                                                                                                                                                                                                                                  |
| `options`     | `array`  | No       | An array of strings used to populate a `<select>` dropdown. If present, the `type` should be `select`.                                                                                                                                                                                                                                    |
| `required`    | `string` | No       | Determines when the field is mandatory. Valid options are `always` or `clean-install`.                                                                                                                                                                                                                                                  |
| `source`      | `string` | No       | **(New)** Specifies the source of the variable's value. If omitted, the value is expected from user input. The only valid option is: <ul><li>`dotenv`: Instructs the UI to render a disabled field, indicating the value is managed securely on the backend via the project's `.env` file. This prevents secrets from being entered in the UI.</li></ul> |
