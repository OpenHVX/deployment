// Read-only deployment preflight. The running controller supplies MONGO_URL.
const mongoose = require('mongoose');

(async () => {
  // Keep a failed observation bounded. Ansible owns the retry interval; a
  // connection failure must never be interpreted as an empty task journal.
  await mongoose.connect(process.env.MONGO_URL, {
    serverSelectionTimeoutMS: 5000,
    connectTimeoutMS: 5000,
  });
  try {
    const count = await mongoose.connection.collection('tasks').countDocuments({
      status: { $in: ['queued', 'sent', 'reconciling'] },
    });
    if (count) throw new Error(`Drain ${count} unresolved task(s) before deployment`);
  } finally {
    await mongoose.disconnect();
  }
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
