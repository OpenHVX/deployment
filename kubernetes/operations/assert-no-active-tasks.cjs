// Read-only deployment preflight. The running controller supplies MONGO_URL.
const mongoose = require('mongoose');

(async () => {
  await mongoose.connect(process.env.MONGO_URL);
  try {
    const count = await mongoose.connection.collection('tasks').countDocuments({
      status: { $in: ['queued', 'sent', 'reconciling'] },
    });
    if (count) throw new Error('Drain unresolved tasks before deployment');
  } finally {
    await mongoose.disconnect();
  }
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
