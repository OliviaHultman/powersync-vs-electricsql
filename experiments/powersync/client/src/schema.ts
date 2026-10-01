import { column, Schema, Table } from '@powersync/node';

// PowerSync adds an `id` (text) column automatically - don't declare it here.
const events = new Table({
  payload: column.text,
  inserted_at: column.text,
});

export const AppSchema = new Schema({ events });
